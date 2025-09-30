#include <iostream>
#include <vector>
#include <string>
#include <random>
#include "commodity.cpp"
#include "multiFactorStrat.cpp"

static std::vector<double> generateSeries(std::mt19937& rng, int length, double start, double drift, double volatility) {
    std::normal_distribution<double> noise(0.0, volatility);
    std::vector<double> series;
    series.reserve(length);
    double value = start;
    for (int i = 0; i < length; ++i) {
        value += drift + noise(rng);
        if (value < 0.0) value = 0.0;
        series.push_back(value);
    }
    return series;
}

int main() {
    std::mt19937 rng(42);

    std::vector<Commodity> data;
    data.reserve(24);

    const int seriesLen = 50;

    std::vector<std::string> names = {
        "CrudeOil", "Brent", "NaturalGas", "Gasoline", "HeatingOil", "Gold", "Silver", "Copper",
        "Aluminum", "Corn", "Wheat", "Soybeans", "Coffee", "Cocoa", "Sugar", "Cotton",
        "LiveCattle", "LeanHogs", "FeederCattle", "Palladium", "Platinum", "Nickel", "Zinc", "Tin"
    };

    std::uniform_real_distribution<double> startDist(10.0, 200.0);
    std::uniform_real_distribution<double> driftDist(-0.5, 0.8);
    std::uniform_real_distribution<double> volDist(0.1, 2.0);
    std::uniform_real_distribution<double> carryDist(-2.0, 2.0);
    std::uniform_real_distribution<double> volLevel(1000.0, 10000.0);

    for (const auto& n : names) {
        double start = startDist(rng);
        double drift = driftDist(rng);
        double vol = volDist(rng);
        auto prices = generateSeries(rng, seriesLen, start, drift, vol);

        // Volumes as positive series around a base level
        double baseVol = volLevel(rng);
        auto volumes = generateSeries(rng, seriesLen, baseVol, 0.0, baseVol * 0.05);

        Commodity c;
        c.name = n;
        c.prices = std::move(prices);
        c.volumes = std::move(volumes);
        c.carry = carryDist(rng);
        data.push_back(std::move(c));
    }

    MultiFactorStrat strat(data);
    strat.evaluateCommodities();
    strat.rank();
    strat.selectRanked();
    strat.display();

    return 0;
}


