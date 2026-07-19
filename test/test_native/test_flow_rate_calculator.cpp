#include <gtest/gtest.h>
#include "FlowRateCalculator.h"

class FlowRateCalculatorTest : public ::testing::Test {
protected:
    FlowRateCalculator calc;
    void SetUp() override { calc.reset(); }
};

// ====== Basic behavior ======

TEST_F(FlowRateCalculatorTest, FirstSampleReturnsZero)
{
    float rate = calc.update(100.0f, 0);
    EXPECT_FLOAT_EQ(rate, 0.0f);
}

TEST_F(FlowRateCalculatorTest, NoChangeReturnsZeroRate)
{
    calc.update(100.0f, 0);
    float rate = calc.update(100.0f, 10000);
    EXPECT_FLOAT_EQ(rate, 0.0f);
}

TEST_F(FlowRateCalculatorTest, InflowReturnsPositiveRate)
{
    calc.update(100.0f, 0);
    // Volume increased by 10L over 30s (0.5 min) → 20 L/min
    float rate = calc.update(110.0f, 30000);
    EXPECT_NEAR(rate, 20.0f, 0.01f);
}

TEST_F(FlowRateCalculatorTest, OutflowReturnsNegativeRate)
{
    calc.update(100.0f, 0);
    // Volume decreased by 10L over 30s (0.5 min) → -20 L/min
    float rate = calc.update(90.0f, 30000);
    EXPECT_NEAR(rate, -20.0f, 0.01f);
}

// ====== Moving average window ======

TEST_F(FlowRateCalculatorTest, MovingAverageSmooths)
{
    // Simulate 3 samples at 10s intervals
    calc.update(100.0f, 0);

    // +6L in 10s → +36 L/min
    calc.update(106.0f, 10000);

    // +3L in 10s → +18 L/min; average of [36, 18] = 27
    float rate = calc.update(109.0f, 20000);
    EXPECT_NEAR(rate, 27.0f, 0.01f);
}

TEST_F(FlowRateCalculatorTest, MovingAverageWithMixedRates)
{
    calc.update(100.0f, 0);

    // +10L in 10s = +60 L/min
    calc.update(110.0f, 10000);

    // -5L in 10s = -30 L/min; avg of [60, -30] = 15
    float rate = calc.update(105.0f, 20000);
    EXPECT_NEAR(rate, 15.0f, 0.01f);
}

// ====== Window expiry ======

TEST_F(FlowRateCalculatorTest, OldSamplesExpireAfterOneMinute)
{
    calc.update(100.0f, 0);

    // +10L at t=10s → 60 L/min
    calc.update(110.0f, 10000);

    // +0L at t=20s → 0 L/min; avg [60, 0] = 30
    calc.update(110.0f, 20000);

    // Now jump to t=71s (first sample at t=10s is >60s old, should expire)
    // +5L in 51s → +5.882 L/min
    // Only samples from t=20s and t=71s remain in window
    // t=20s: 0 L/min, t=71s: 5.882 L/min; avg = 2.941
    float rate = calc.update(115.0f, 71000);
    EXPECT_NEAR(rate, 2.94f, 0.1f);
}

TEST_F(FlowRateCalculatorTest, AllSamplesExpiredReturnsCurrentOnly)
{
    calc.update(100.0f, 0);
    calc.update(110.0f, 10000);  // +60 L/min

    // Jump forward 2 minutes — all old samples expire
    // +5L in 120s → 2.5 L/min
    float rate = calc.update(115.0f, 130000);
    EXPECT_NEAR(rate, 2.5f, 0.01f);
}

// ====== Reset ======

TEST_F(FlowRateCalculatorTest, ResetClearsState)
{
    calc.update(100.0f, 0);
    calc.update(110.0f, 10000);
    calc.reset();

    EXPECT_FLOAT_EQ(calc.getRate(), 0.0f);

    // After reset, first sample returns 0 again
    float rate = calc.update(50.0f, 20000);
    EXPECT_FLOAT_EQ(rate, 0.0f);
}

TEST_F(FlowRateCalculatorTest, GetRateMatchesLastUpdate)
{
    calc.update(100.0f, 0);
    calc.update(110.0f, 10000);

    EXPECT_FLOAT_EQ(calc.getRate(), 60.0f);
}

// ====== Precision with large volumes ======

TEST_F(FlowRateCalculatorTest, LargeVolumePrecision)
{
    // 5000L tank (5m³), small level change
    float totalVolume = 5000.0f;

    calc.update(0.5000f * totalVolume, 0);       // 2500.0L
    calc.update(0.5001f * totalVolume, 10000);    // 2500.5L

    // +0.5L in 10s → 3.0 L/min
    float rate = calc.getRate();
    EXPECT_NEAR(rate, 3.0f, 0.1f);
}

TEST_F(FlowRateCalculatorTest, SmallFlowRateNotLostToRounding)
{
    // 5000L tank, very small change
    float totalVolume = 5000.0f;

    calc.update(0.50000f * totalVolume, 0);        // 2500.0L
    calc.update(0.50002f * totalVolume, 10000);     // 2500.1L

    // +0.1L in 10s → 0.6 L/min
    float rate = calc.getRate();
    EXPECT_NEAR(rate, 0.6f, 0.05f);
}

// ====== Steady-state moving average convergence ======

TEST_F(FlowRateCalculatorTest, SteadyFlowConvergesToConstantRate)
{
    // Simulate constant inflow: +1L every 10s = +6 L/min
    calc.update(100.0f, 0);
    float rate = 0;
    for (int i = 1; i <= 6; i++) {
        rate = calc.update(100.0f + i * 1.0f, i * 10000);
    }
    // After 6 samples at constant rate, average should be exactly 6 L/min
    EXPECT_NEAR(rate, 6.0f, 0.01f);
}

// ====== MAX_SAMPLES limit ======

TEST_F(FlowRateCalculatorTest, MaxSamplesLimitPreventsUnboundedGrowth)
{
    // Add many samples rapidly to test MAX_SAMPLES enforcement
    calc.update(100.0f, 0);
    for (int i = 1; i <= 200; i++) {
        calc.update(100.0f + i * 0.1f, i * 100);
    }
    // Should not crash or grow beyond MAX_SAMPLES
    float rate = calc.getRate();
    EXPECT_GT(rate, 0.0f);  // Should still calculate a valid rate
}
