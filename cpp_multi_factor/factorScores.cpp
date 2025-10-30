#pragma once

struct FactorScores {
    double momentum  = 0.0;
    double carry = 0.0;
    double volume = 0.0;
    double dollarBeta = 0.0;  // CRITICAL 1: Dollar beta factor
    double inflationBeta = 0.0;  // CRITICAL 3: Inflation beta factor (metals only)
    double totalScore = 0.0;
    double zScore = 0.0;
};