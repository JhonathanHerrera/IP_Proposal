# C++ Multi-Factor Strategy

This folder contains a C++ implementation that ranks commodities by momentum, carry, and volume. It includes synthetic data generation for quick testing.

## Build and Run

With MinGW g++ available on PATH:

`powershell
cd cpp_multi_factor
g++ -std=c++17 -O2 main.cpp -o run_ip.exe
.\run_ip.exe
`

If you prefer to build from your original workspace, compile from AlgoGator/ip and copy the binary here if needed.

## Files
- main.cpp
- multiFactorStrat.cpp
- factorCalc.cpp
- factorScores.cpp
- commodity.cpp
