#pragma once
#include <iostream>
#include <string>
#include <vector>

struct Commodity {
    std::string name;
    std::vector<double> prices;
    std::vector<double> volumes;
    double carry;
};
