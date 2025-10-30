#pragma once
#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <string>
#include <map>
#include "commodity.cpp"

class CSVLoader {
public:
    static std::vector<Commodity> load(const std::string& filename) {
        std::ifstream file(filename);
        if (!file.is_open()) {
            throw std::runtime_error("Error: Could not open " + filename);
        }

        std::string line;
        std::getline(file, line); // skip header

        std::map<std::string, Commodity> bySymbol;

        while (std::getline(file, line)) {
            std::stringstream ss(line);
            std::string symbol, date, priceStr, volumeStr, carryStr, dollarStr;

            std::getline(ss, symbol, ',');
            std::getline(ss, date, ',');
            std::getline(ss, priceStr, ',');
            std::getline(ss, volumeStr, ',');
            std::getline(ss, carryStr, ',');
            std::getline(ss, dollarStr, ',');  // CRITICAL 1: Load dollar index

            if (symbol.empty() || priceStr.empty() || volumeStr.empty() || carryStr.empty() || dollarStr.empty())
                continue;

            double price = std::stod(priceStr);
            double volume = std::stod(volumeStr);
            double carry = std::stod(carryStr);
            double dollar = std::stod(dollarStr);  // CRITICAL 1: Parse dollar index

            auto& c = bySymbol[symbol];
            c.name = symbol;
            c.prices.push_back(price);
            c.volumes.push_back(volume);
            c.dollarIndex.push_back(dollar);  // CRITICAL 1: Store dollar index
            c.inflationExpectations.push_back(carry);  // CRITICAL 3: Use carry as inflation expectations (T5YIFR)
            c.carry = carry; // just overwrite with the latest carry
        }

        std::vector<Commodity> commodities;
        for (auto& kv : bySymbol) {
            commodities.push_back(std::move(kv.second));
        }

        return commodities;
    }
};