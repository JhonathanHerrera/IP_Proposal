#pragma once
#include <iostream>
#include <string>
#include <vector>

struct Commodity {
    std::string name;
    std::vector<double> prices;
    std::vector<double> volumes;
    std::vector<double> dollarIndex;  // CRITICAL 1: Dollar index data for dollar beta
    std::vector<double> inflationExpectations;  // CRITICAL 3: Inflation expectations for inflation beta
    double carry;
};
