#include <iostream>
#include <vector>
#include <string>
#include <map>
#include <set>
#include <algorithm>
#include <numeric>
#include <cmath>
#include <fstream>
#include "factorScores.cpp"
#include "commodity.cpp"
#include "factorCalc.cpp"

class MultiFactorStrat {
private: 
    std::vector<Commodity> commodities;
    std::map<std::string, FactorScores> commodityScores;
    std::vector<std::pair<std::string, FactorScores>> ranked;
    std::map<int, std::pair<std::string, FactorScores>> finalRankedCommodities; // key = rank, value = (commodity name, scores)
    
    // CRITICAL 4: 5-Day Minimum Holding Period tracking
    std::map<std::string, int> positionEntryDays; // {commodity: entry_day}
    int currentDay = 0;
    int minHoldDays = 5;

public:
    MultiFactorStrat(const std::vector<Commodity>& data) : commodities(data) {}

    void evaluateCommodities() {
        FactorCalculation fc;
        
        // First pass: calculate all raw factors
        for (const auto& commodity : commodities) {
            FactorScores fs;
            fs.momentum = fc.calcMomentum(commodity.prices);
            fs.carry = fc.calcCarry(commodity.carry);
            
            // CRITICAL 2: Calculate volume/inventory with energy sign flip
            bool isEnergy = (commodity.name == "CL" || commodity.name == "RB");
            fs.volume = fc.calcVolume(commodity.volumes, isEnergy);
            
            // CRITICAL 1: Calculate dollar beta with metal sign flip
            bool isMetal = (commodity.name == "GC" || commodity.name == "SI" || 
                           commodity.name == "HG" || commodity.name == "PL");
            fs.dollarBeta = fc.calcDollarBeta(commodity.prices, commodity.dollarIndex, isMetal);
            
            // CRITICAL 3: Calculate inflation beta (metals only)
            fs.inflationBeta = fc.calcInflationBeta(commodity.prices, commodity.inflationExpectations, isMetal);
            
            // Align with PDF: use inflation beta as 'carry' for metals; zero carry for non-metals
            if (isMetal) {
                fs.carry = fs.inflationBeta;  // metals: carry = inflation beta
                fs.inflationBeta = 0.0;       // avoid double counting
            } else {
                fs.carry = 0.0;               // non-metals: no cross-sectional carry contribution
                fs.inflationBeta = 0.0;       // ensure not counted separately
            }

            commodityScores[commodity.name] = fs;
        }
        
        // BONUS 1: Proper winsorization (5th/95th) and cross-sectional z-scoring per factor
        // Collect factor arrays
        std::vector<double> momVals, carryVals, volVals, dbVals, ibVals;
        momVals.reserve(commodityScores.size());
        carryVals.reserve(commodityScores.size());
        volVals.reserve(commodityScores.size());
        dbVals.reserve(commodityScores.size());
        ibVals.reserve(commodityScores.size());
        for (const auto& kv : commodityScores) {
            const auto& fs = kv.second;
            momVals.push_back(fs.momentum);
            carryVals.push_back(fs.carry);
            volVals.push_back(fs.volume);
            dbVals.push_back(fs.dollarBeta);
            ibVals.push_back(fs.inflationBeta);
        }
        // Compute bounds
        const double L = 0.05, U = 0.95;
        double momLo = fc.quantile(momVals, L), momHi = fc.quantile(momVals, U);
        double carLo = fc.quantile(carryVals, L), carHi = fc.quantile(carryVals, U);
        double volLo = fc.quantile(volVals, L), volHi = fc.quantile(volVals, U);
        double dbLo  = fc.quantile(dbVals,  L), dbHi  = fc.quantile(dbVals,  U);
        double ibLo  = fc.quantile(ibVals,  L), ibHi  = fc.quantile(ibVals,  U);
        
        // Clamp (winsorize)
        for (auto& kv : commodityScores) {
            auto& fs = kv.second;
            fs.momentum     = fc.clamp(fs.momentum,     momLo, momHi);
            fs.carry        = fc.clamp(fs.carry,        carLo, carHi);
            fs.volume       = fc.clamp(fs.volume,       volLo, volHi);
            fs.dollarBeta   = fc.clamp(fs.dollarBeta,   dbLo,  dbHi);
            fs.inflationBeta= fc.clamp(fs.inflationBeta,ibLo,  ibHi);
        }
        
        // Z-score per factor
        auto zscore = [](const std::vector<double>& vals){
            double mean = std::accumulate(vals.begin(), vals.end(), 0.0) / std::max<size_t>(1, vals.size());
            double ss = 0.0; for (double v : vals) { double d = v - mean; ss += d*d; }
            double sd = std::sqrt(ss / std::max<size_t>(1, vals.size()));
            if (sd == 0.0) sd = 1.0;
            std::vector<double> out; out.reserve(vals.size());
            for (double v : vals) out.push_back((v - mean) / sd);
            return out;
        };
        
        // Re-collect clamped values
        momVals.clear(); carryVals.clear(); volVals.clear(); dbVals.clear(); ibVals.clear();
        std::vector<std::string> names; names.reserve(commodityScores.size());
        for (const auto& kv : commodityScores) {
            names.push_back(kv.first);
            const auto& fs = kv.second;
            momVals.push_back(fs.momentum);
            carryVals.push_back(fs.carry);
            volVals.push_back(fs.volume);
            dbVals.push_back(fs.dollarBeta);
            ibVals.push_back(fs.inflationBeta);
        }
        
        auto momZ = zscore(momVals);
        auto carZ = zscore(carryVals);
        auto volZ = zscore(volVals);
        auto dbZ  = zscore(dbVals);
        auto ibZ  = zscore(ibVals);
        
        // Assign z-scores back and compute composite as sum of z-scores
        for (size_t i = 0; i < names.size(); ++i) {
            auto& fs = commodityScores[names[i]];
            fs.momentum = momZ[i];
            fs.carry = carZ[i];
            fs.volume = volZ[i];
            fs.dollarBeta = dbZ[i];
            fs.inflationBeta = ibZ[i];
            fs.totalScore = momZ[i] + carZ[i] + volZ[i] + dbZ[i] + ibZ[i];
        }
    }

    void rank() {
        ranked = std::vector<std::pair<std::string, FactorScores>>(commodityScores.begin(), commodityScores.end());

        std::sort(ranked.begin(), ranked.end(),
                  [](const auto& a, const auto& b) {
                      return a.second.totalScore > b.second.totalScore;
                  });
    }

    void zScore() {
        if (ranked.empty()) rank(); 

        double sum = 0.0;
        for (const auto& a : ranked) sum += a.second.totalScore;
        double mean = sum / ranked.size();

        double sq_sum = 0.0;
        for (const auto& a : ranked) {
            sq_sum += std::pow(a.second.totalScore - mean, 2);
        }
        double stddev = std::sqrt(sq_sum / ranked.size());
        if (stddev == 0.0) stddev = 1.0;

        for (auto& a : ranked) {
            a.second.zScore = (a.second.totalScore - mean) / stddev;
        }
    }

    void selectRanked() {
        if (ranked.empty()) rank();
        zScore();
    
        int n = ranked.size();
        int k = std::max(1, static_cast<int>(std::ceil(0.2 * n))); // top/bottom 20%
    
        // CRITICAL 4: Apply 5-day minimum holding period
        std::vector<std::string> targetLongs;
        std::vector<std::string> targetShorts;
        std::vector<std::string> finalLongs;
        std::vector<std::string> finalShorts;
        
        // Get target positions (top/bottom 20%)
        for (int i = 0; i < k; i++) {
            targetLongs.push_back(ranked[i].first);
        }
        for (int i = n - k; i < n; i++) {
            targetShorts.push_back(ranked[i].first);
        }
        
        // Get current positions (from previous selection)
        std::set<std::string> currentLongs, currentShorts;
        for (const auto& [rank, entry] : finalRankedCommodities) {
            std::string name = entry.first;
            if (name.find("(LONG)") != std::string::npos) {
                std::string commodity = name.substr(0, name.find(" (LONG)"));
                currentLongs.insert(commodity);
            } else if (name.find("(SHORT)") != std::string::npos) {
                std::string commodity = name.substr(0, name.find(" (SHORT)"));
                currentShorts.insert(commodity);
            }
        }
        
        // Apply 5-day hold rule for existing positions
        for (const auto& commodity : currentLongs) {
            if (positionEntryDays.find(commodity) != positionEntryDays.end()) {
                int daysHeld = currentDay - positionEntryDays[commodity];
                if (daysHeld < minHoldDays) {
                    // Force hold (haven't met minimum)
                    finalLongs.push_back(commodity);
                } else if (std::find(targetLongs.begin(), targetLongs.end(), commodity) != targetLongs.end()) {
                    // Still in target, keep holding
                    finalLongs.push_back(commodity);
                }
                // else: exit allowed (>5 days and not in target)
            }
        }
        
        for (const auto& commodity : currentShorts) {
            if (positionEntryDays.find(commodity) != positionEntryDays.end()) {
                int daysHeld = currentDay - positionEntryDays[commodity];
                if (daysHeld < minHoldDays) {
                    finalShorts.push_back(commodity);
                } else if (std::find(targetShorts.begin(), targetShorts.end(), commodity) != targetShorts.end()) {
                    finalShorts.push_back(commodity);
                }
            }
        }
        
        // Add new positions from target
        for (const auto& commodity : targetLongs) {
            if (std::find(finalLongs.begin(), finalLongs.end(), commodity) == finalLongs.end() &&
                std::find(finalShorts.begin(), finalShorts.end(), commodity) == finalShorts.end()) {
                finalLongs.push_back(commodity);
                positionEntryDays[commodity] = currentDay;
            }
        }
        
        for (const auto& commodity : targetShorts) {
            if (std::find(finalShorts.begin(), finalShorts.end(), commodity) == finalShorts.end() &&
                std::find(finalLongs.begin(), finalLongs.end(), commodity) == finalLongs.end()) {
                finalShorts.push_back(commodity);
                positionEntryDays[commodity] = currentDay;
            }
        }
        
        // BONUS 2: Apply position limits (15% maximum per commodity)
        const double MAX_POSITION_SIZE = 0.15; // 15% cap per commodity
        
        // Calculate target weights
        std::map<std::string, double> targetWeights;
        double longWeight = 0.5 / std::max<size_t>(1, finalLongs.size());
        double shortWeight = -0.5 / std::max<size_t>(1, finalShorts.size());
        
        for (const auto& commodity : finalLongs) {
            targetWeights[commodity] = longWeight;
        }
        for (const auto& commodity : finalShorts) {
            targetWeights[commodity] = shortWeight;
        }
        
        // Apply position cap
        std::map<std::string, double> cappedWeights;
        for (const auto& [commodity, weight] : targetWeights) {
            double capped = weight;
            if (capped >  MAX_POSITION_SIZE) capped =  MAX_POSITION_SIZE;
            if (capped < -MAX_POSITION_SIZE) capped = -MAX_POSITION_SIZE;
            cappedWeights[commodity] = capped;
        }
        
        // Renormalize to maintain 50/50 long/short
        double longSum = 0.0, shortSum = 0.0;
        for (const auto& [commodity, weight] : cappedWeights) {
            if (weight > 0) longSum += weight; else shortSum += std::abs(weight);
        }
        
        // Final weights with renormalization
        std::map<std::string, double> finalWeights;
        for (const auto& [commodity, weight] : cappedWeights) {
            if (weight > 0 && longSum > 0) {
                finalWeights[commodity] = weight * (0.5 / longSum);
            } else if (weight < 0 && shortSum > 0) {
                finalWeights[commodity] = weight * (0.5 / shortSum);
            }
        }
        
        // Update final ranked commodities with position weights
        finalRankedCommodities.clear();
        int rank = 1;
        
        // Add longs with weights
        for (const auto& commodity : finalLongs) {
            if (finalWeights.find(commodity) != finalWeights.end()) {
                // Find the original ranking for this commodity
                for (const auto& pair : ranked) {
                    if (pair.first == commodity) {
                        std::string displayName = commodity + " (LONG " + 
                            std::to_string(static_cast<int>(finalWeights[commodity] * 100)) + "%)";
                        finalRankedCommodities[rank++] = {displayName, pair.second};
                        break;
                    }
                }
            }
        }
        
        // Add shorts with weights
        for (const auto& commodity : finalShorts) {
            if (finalWeights.find(commodity) != finalWeights.end()) {
                // Find the original ranking for this commodity
                for (const auto& pair : ranked) {
                    if (pair.first == commodity) {
                        std::string displayName = commodity + " (SHORT " + 
                            std::to_string(static_cast<int>(std::abs(finalWeights[commodity]) * 100)) + "%)";
                        finalRankedCommodities[rank++] = {displayName, pair.second};
                        break;
                    }
                }
            }
        }
    }
    
    // Method to advance to next day (for holding period tracking)
    void advanceDay() {
        currentDay++;
    }
    
    // BONUS 3: Partial rebalancing logic (simplified for C++ demo)
    bool shouldRebalance(const std::string& commodity, double currentWeight, double targetWeight) {
        const double REBALANCE_THRESHOLD = 0.03; // 3% drift
        double drift = std::abs(targetWeight - currentWeight);
        return drift > REBALANCE_THRESHOLD;
    }
    
    // Method to simulate partial rebalancing (for demonstration)
    void applyPartialRebalancing() {
        std::cout << "\nBONUS 3: Partial Rebalancing Analysis:\n";
        std::cout << "Commodity | Current | Target | Drift | Rebalance?\n";
        std::cout << "------------------------------------------------\n";
        
        // Simulate some current vs target weights
        std::map<std::string, double> currentWeights = {
            {"GF.V.0", 0.12}, {"RB.V.0", 0.12}, {"ZL.V.0", 0.12}, {"ZM.V.0", 0.12},
            {"GC.V.0", -0.12}, {"SI.V.0", -0.12}, {"ZW.V.0", -0.12}, {"KE.V.0", -0.12}
        };
        
        std::map<std::string, double> targetWeights = {
            {"GF.V.0", 0.125}, {"RB.V.0", 0.115}, {"ZL.V.0", 0.12}, {"ZM.V.0", 0.13},
            {"GC.V.0", -0.11}, {"SI.V.0", -0.125}, {"ZW.V.0", -0.12}, {"KE.V.0", -0.115}
        };
        
        for (const auto& [commodity, currentWeight] : currentWeights) {
            if (targetWeights.find(commodity) != targetWeights.end()) {
                double targetWeight = targetWeights[commodity];
                bool shouldRebalance = this->shouldRebalance(commodity, currentWeight, targetWeight);
                
                std::cout << commodity << " | " << currentWeight << " | " 
                         << targetWeight << " | " << std::abs(targetWeight - currentWeight) 
                         << " | " << (shouldRebalance ? "YES" : "NO") << "\n";
            }
        }
    }

    void display() {
        std::cout << "Final Selected Commodities (Top/Bottom 20%):\n";
        std::cout << "Rank | Name        | Mom     | Carry   | Volume  | Dollar  | Infl    | Total   | Z-Score\n";
        std::cout << "-------------------------------------------------------------------------------------------\n";
    
        // Also save to CSV file for Excel
        std::ofstream csvFile("positions_table.csv");
        csvFile << "Rank,Name,Position,Weight,Momentum,Carry,Volume,Dollar_Beta,Inflation_Beta,Total_Score,Z_Score\n";
        
        for (const auto& [rank, entry] : finalRankedCommodities) {
            const std::string& name = entry.first;
            const FactorScores& fs = entry.second;
            
            // Determine position type and weight
            std::string position = (name.find("LONG") != std::string::npos) ? "LONG" : "SHORT";
            std::string weight = "12%"; // Default weight
            
            // Extract commodity name without position info
            std::string commodityName = name.substr(0, name.find(" ("));
    
            std::cout << rank << "    | "
                      << name << " | "
                      << fs.momentum << " | "
                      << fs.carry << " | "
                      << fs.volume << " | "
                      << fs.dollarBeta << " | "
                      << fs.inflationBeta << " | "
                      << fs.totalScore << " | "
                      << fs.zScore << "\n";
                      
            // Write to CSV
            csvFile << rank << ","
                    << commodityName << ","
                    << position << ","
                    << weight << ","
                    << fs.momentum << ","
                    << fs.carry << ","
                    << fs.volume << ","
                    << fs.dollarBeta << ","
                    << fs.inflationBeta << ","
                    << fs.totalScore << ","
                    << fs.zScore << "\n";
        }
        
        csvFile.close();
        std::cout << "\n✅ Table data saved to 'positions_table.csv' for Excel analysis\n";
    }
};
