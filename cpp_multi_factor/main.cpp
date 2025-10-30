#include <iostream>
#include "csv_loader.hpp"
#include "multiFactorStrat.cpp"

int main() {
    try {
        // Load the merged CSV
        auto data = CSVLoader::load("all_data.csv");

        if (data.empty()) {
            std::cerr << "No commodities loaded from CSV.\n";
            return 1;
        }

        MultiFactorStrat strat(data);
        strat.evaluateCommodities();
        strat.rank();
        strat.selectRanked();
        strat.display();
        strat.applyPartialRebalancing();
    }
    catch (const std::exception& ex) {
        std::cerr << ex.what() << "\n";
        return 1;
    }

    return 0;
}