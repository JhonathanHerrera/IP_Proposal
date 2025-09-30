#include <iostream>
#include <vector>
#include <string>
#include <map>
#include <algorithm>
#include <numeric>
#include <cmath>
#include "factorScores.cpp"
#include "commodity.cpp"
#include "factorCalc.cpp"

class MultiFactorStrat {
private: 
    std::vector<Commodity> commodities;
    std::map<std::string, FactorScores> commodityScores;
    std::vector<std::pair<std::string, FactorScores>> ranked;
    std::map<int, std::pair<std::string, FactorScores>> finalRankedCommodities; // key = rank, value = (commodity name, scores)

public:
    MultiFactorStrat(const std::vector<Commodity>& data) : commodities(data) {}

    void evaluateCommodities() {
        FactorCalculation fc;
        for (const auto& commodity : commodities) {
            FactorScores fs;
            fs.momentum = fc.calcMomentum(commodity.prices);
            fs.carry = fc.calcCarry(commodity.carry);
            fs.volume = fc.calcVolume(commodity.volumes);
            fs.totalScore = fs.momentum + fs.carry + fs.volume;

            commodityScores[commodity.name] = fs;
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
    
        // Top k (LONG)
        for (int i = 0; i < k; i++) {
            finalRankedCommodities[i+1] = {ranked[i].first + " (LONG)", ranked[i].second};
        }
        // Bottom k (SHORT)
        for (int i = n - k; i < n; i++) {
            finalRankedCommodities[i+1] = {ranked[i].first + " (SHORT)", ranked[i].second};
        }
    }

    void display() {
        std::cout << "Final Selected Commodities (Top/Bottom 20%):\n";
        std::cout << "Rank | Name        | Mom     | Carry   | Volume  | Total   | Z-Score\n";
        std::cout << "-------------------------------------------------------------------\n";
    
        for (const auto& [rank, entry] : finalRankedCommodities) {
            const std::string& name = entry.first;
            const FactorScores& fs = entry.second;
    
            std::cout << rank << "    | "
                      << name << " | "
                      << fs.momentum << " | "
                      << fs.carry << " | "
                      << fs.volume << " | "
                      << fs.totalScore << " | "
                      << fs.zScore << "\n";
        }
    }
};
