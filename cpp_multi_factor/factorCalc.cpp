#include <iostream>
#include <vector>
#include <string>
#include <map>
#include <algorithm>
#include <numeric>
#include <cmath>


class FactorCalculation {
public:


    double calcMomentum(const std::vector<double>& prices) {
        if (prices.size() < 2) return 0.0; //We dont have enough data to calculate the momentum
        return prices.back() - prices.front();
    }

    double calcCarry(double carry) {
        //Or do we calculate the carry?
        return carry;
    }

    double calcVolume(const std::vector<double>& volumes, bool isEnergy = false) {
        if (volumes.empty()) return 0.0; //We dont have enough data to calculate the volume
        
        double volumeSum = std::accumulate(volumes.begin(), volumes.end(), 0.0);
        
        // CRITICAL 2: Flip sign for energy commodities
        // Why? High inventory (crude stocks) is bearish for energy prices
        // We want high inventory to produce LOW scores for SHORT positions
        if (isEnergy) {
            volumeSum = -volumeSum;
        }
        
        return volumeSum;
    }

    // CRITICAL 1: Calculate dollar beta (90-day rolling correlation with USD)
    double calcDollarBeta(const std::vector<double>& prices, const std::vector<double>& dollarIndex, bool isMetal = false) {
        if (prices.size() < 90 || dollarIndex.size() < 90) {
            return 0.0; // Not enough data for 90-day correlation
        }
        
        // Calculate returns for both price and dollar index
        std::vector<double> priceReturns;
        std::vector<double> dollarReturns;
        
        for (size_t i = 1; i < prices.size(); ++i) {
            if (prices[i-1] != 0 && dollarIndex[i-1] != 0) {
                priceReturns.push_back((prices[i] - prices[i-1]) / prices[i-1]);
                dollarReturns.push_back((dollarIndex[i] - dollarIndex[i-1]) / dollarIndex[i-1]);
            }
        }
        
        if (priceReturns.size() < 90) return 0.0;
        
        // Calculate 90-day rolling correlation
        size_t startIdx = priceReturns.size() - 90;
        double sumX = 0.0, sumY = 0.0, sumXY = 0.0, sumX2 = 0.0, sumY2 = 0.0;
        
        for (size_t i = startIdx; i < priceReturns.size(); ++i) {
            double x = priceReturns[i];
            double y = dollarReturns[i];
            sumX += x;
            sumY += y;
            sumXY += x * y;
            sumX2 += x * x;
            sumY2 += y * y;
        }
        
        double n = 90.0;
        double numerator = n * sumXY - sumX * sumY;
        double denominator = std::sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
        
        if (denominator == 0.0) return 0.0;
        
        double correlation = numerator / denominator;
        
        // CRITICAL: Flip sign for metals (negative correlation with dollar is GOOD for metals)
        if (isMetal) {
            correlation = -correlation;
        }
        
        return correlation;
    }

    // CRITICAL 3: Calculate inflation beta (metals only)
    // This measures if metals rise when inflation expectations rise (true inflation hedge)
    double calcInflationBeta(const std::vector<double>& prices, const std::vector<double>& inflationExpectations, bool isMetal = false) {
        if (!isMetal) {
            return 0.0; // Non-metals don't use inflation beta
        }
        
        if (prices.size() < 90 || inflationExpectations.size() < 90) {
            return 0.0; // Not enough data for 90-day correlation
        }
        
        // Calculate returns for both price and inflation expectations
        std::vector<double> priceReturns;
        std::vector<double> inflationChanges;
        
        for (size_t i = 1; i < prices.size(); ++i) {
            if (prices[i-1] != 0 && inflationExpectations[i-1] != 0) {
                priceReturns.push_back((prices[i] - prices[i-1]) / prices[i-1]);
                inflationChanges.push_back(inflationExpectations[i] - inflationExpectations[i-1]); // Absolute change, not %
            }
        }
        
        if (priceReturns.size() < 90) return 0.0;
        
        // Calculate 90-day rolling correlation
        size_t startIdx = priceReturns.size() - 90;
        double sumX = 0.0, sumY = 0.0, sumXY = 0.0, sumX2 = 0.0, sumY2 = 0.0;
        
        for (size_t i = startIdx; i < priceReturns.size(); ++i) {
            double x = priceReturns[i];
            double y = inflationChanges[i];
            sumX += x;
            sumY += y;
            sumXY += x * y;
            sumX2 += x * x;
            sumY2 += y * y;
        }
        
        double n = 90.0;
        double numerator = n * sumXY - sumX * sumY;
        double denominator = std::sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
        
        if (denominator == 0.0) return 0.0;
        
        double correlation = numerator / denominator;
        
        // High correlation = metal working as inflation hedge = GOOD = high score = LONG
        return correlation;
    }

    // BONUS 1 helpers: proper quantile and clamp
    double quantile(std::vector<double> values, double pct) {
        if (values.empty()) return 0.0;
        if (pct <= 0.0) return *std::min_element(values.begin(), values.end());
        if (pct >= 1.0) return *std::max_element(values.begin(), values.end());
        std::sort(values.begin(), values.end());
        double idx = pct * (values.size() - 1);
        size_t lo = static_cast<size_t>(std::floor(idx));
        size_t hi = static_cast<size_t>(std::ceil(idx));
        if (lo == hi) return values[lo];
        double w = idx - lo;
        return values[lo] * (1.0 - w) + values[hi] * w;
    }

    double clamp(double value, double lo, double hi) {
        return std::max(lo, std::min(hi, value));
    }

};