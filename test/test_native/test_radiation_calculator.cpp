#include <gtest/gtest.h>
#include "RadiationCalculator.h"

class RadiationCalculatorTest : public ::testing::Test {
protected:
    RadiationCalculator calc;
    void SetUp() override { calc.reset(); }
};

// --- CPM calculation ---

TEST_F(RadiationCalculatorTest, SingleClickGivesCPM)
{
    calc.calculate(5, 120.0);
    EXPECT_EQ(calc.getCPM(), 5);
}

TEST_F(RadiationCalculatorTest, AccumulatesClicksOverTime)
{
    calc.calculate(3, 120.0);
    calc.calculate(7, 120.0);
    EXPECT_EQ(calc.getCPM(), 10);
}

TEST_F(RadiationCalculatorTest, BufferLimitedTo60Entries)
{
    // Fill 60 entries with 1 click each
    for (int i = 0; i < 60; i++) {
        calc.calculate(1, 120.0);
    }
    EXPECT_EQ(calc.getCPM(), 60);

    // 61st entry should drop the first
    calc.calculate(1, 120.0);
    EXPECT_EQ(calc.getCPM(), 60);
}

// --- Dose calculation ---

TEST_F(RadiationCalculatorTest, DoseCalculation)
{
    calc.calculate(120, 120.0);
    EXPECT_FLOAT_EQ(calc.getDose(), 1.0f);
}

TEST_F(RadiationCalculatorTest, DoseWithDifferentTubeFactor)
{
    calc.calculate(60, 60.0);
    EXPECT_FLOAT_EQ(calc.getDose(), 1.0f);
}

TEST_F(RadiationCalculatorTest, ZeroClicksZeroDose)
{
    calc.calculate(0, 120.0);
    EXPECT_FLOAT_EQ(calc.getDose(), 0.0f);
}

// --- Graph aggregation ---

TEST_F(RadiationCalculatorTest, GraphNotUpdatedBeforeSpanComplete)
{
    calc.calculate(10, 120.0);
    calc.aggregateGraph(100);
    EXPECT_TRUE(calc.getGraphData().empty());
}

TEST_F(RadiationCalculatorTest, GraphUpdatedAfterSpanComplete)
{
    int spanSize = 5;
    for (int i = 0; i < spanSize; i++) {
        calc.calculate(10, 120.0);
        calc.aggregateGraph(spanSize);
    }
    EXPECT_EQ(calc.getGraphData().size(), 1u);
}

TEST_F(RadiationCalculatorTest, GraphBufferLimitedTo128)
{
    int spanSize = 1;
    for (int i = 0; i < 200; i++) {
        calc.calculate(10, 120.0);
        calc.aggregateGraph(spanSize);
    }
    EXPECT_LE(calc.getGraphData().size(), 128u);
}

// --- Reset ---

TEST_F(RadiationCalculatorTest, ResetClearsAll)
{
    calc.calculate(10, 120.0);
    calc.aggregateGraph(1);
    calc.reset();

    EXPECT_EQ(calc.getCPM(), 0);
    EXPECT_FLOAT_EQ(calc.getDose(), 0.0f);
    EXPECT_TRUE(calc.getGraphData().empty());
    EXPECT_TRUE(calc.getSpanData().empty());
    EXPECT_EQ(calc.getSpanPointer(), 0);
}

// ====== Dead-time (saturation) correction ======

TEST(RadiationCalculatorDeadTime, DisabledByDefault)
{
    RadiationCalculator calc;
    for (int i = 0; i < 60; i++) calc.calculate(100, 120);
    // No dead time -> uncorrected: 100*60 = 6000 CPM
    EXPECT_EQ(calc.getCPM(), 6000);
}

TEST(RadiationCalculatorDeadTime, CorrectsHighCountRates)
{
    RadiationCalculator calc;
    // 60 CPM == 1 CPS; tau = 100us -> m = 1 / (1 - 0.0001) ≈ 1.0001 CPS
    for (int i = 0; i < 60; i++) calc.calculate(1, 120, 100);
    EXPECT_EQ(calc.getCPM(), 60);  // correction negligible at low rates, rounds back to 60
}

TEST(RadiationCalculatorDeadTime, VisibleAtHighRates)
{
    RadiationCalculator calc;
    // 6000 observed -> 100 CPS; tau = 100us -> corrected = 60*100/(1-0.01) = 6060.6 CPM
    for (int i = 0; i < 60; i++) calc.calculate(100, 120, 100);
    EXPECT_NEAR(calc.getCPM(), 6061, 5);
    EXPECT_GT(calc.getCPM(), 6000);
}

TEST(RadiationCalculatorDeadTime, SaturatedTubeNotInfinite)
{
    RadiationCalculator calc;
    // Above 90% of 1/tau the correction is skipped (no runaway values)
    // tau = 200us -> 1/tau = 5000 CPS; push 4800 CPS-equivalent clicks
    for (int i = 0; i < 60; i++) calc.calculate(4800 * 60 / 60, 120, 200);  // 4800 CPS
    // obs cps*tau = 4800*200e-6 = 0.96 > 0.9 -> no correction
    EXPECT_EQ(calc.getCPM(), 288000);
}

// ====== 5-minute dose average ======

TEST(RadiationCalculatorAvg5m, EqualsConstantDoseAtSteadyState)
{
    RadiationCalculator calc;
    // 120 CPM at tube factor 120 -> 1.0 uSv/h; >340 samples so the 300s
    // window holds only full-window (1.0) readings after the 60s ramp
    for (int i = 0; i < 360; i++) calc.calculate(2, 120);
    EXPECT_NEAR(calc.getDoseAvg5m(), 1.0f, 0.01f);
}

TEST(RadiationCalculatorAvg5m, SmoothsTransient)
{
    RadiationCalculator calc;
    for (int i = 0; i < 60; i++) calc.calculate(0, 120);   // quiet minute
    calc.calculate(120, 120);                               // one hot second (1.0 uSv/h)
    // 1.0 over 61 observations -> avg ~0.0164
    EXPECT_NEAR(calc.getDoseAvg5m(), 1.0f / 61.0f, 0.005f);
}

TEST(RadiationCalculatorAvg5m, WindowLimitedToFiveMinutes)
{
    RadiationCalculator calc;
    for (int i = 0; i < 400; i++) calc.calculate(2, 120);  // 1.0 uSv/h
    EXPECT_NEAR(calc.getDoseAvg5m(), 1.0f, 0.01f);

    for (int i = 0; i < 300; i++) calc.calculate(0, 120);  // quiet
    // Window now holds only the drain-down tail of the 60s CPM window
    EXPECT_LT(calc.getDoseAvg5m(), 0.15f);

    for (int i = 0; i < 100; i++) calc.calculate(0, 120);
    EXPECT_NEAR(calc.getDoseAvg5m(), 0.0f, 0.001f);
}
