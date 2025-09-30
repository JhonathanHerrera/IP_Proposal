#include <iostream>
#include <vector>
#include <string>
#include <map>
#include <algorithm>
#include <numeric>


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

    double calcVolume(const std::vector<double>& volumes) {
        if (volumes.empty()) return 0.0; //We dont have enough data to calculate the volume
        return std::accumulate(volumes.begin(), volumes.end(), 0.0);
    }

};