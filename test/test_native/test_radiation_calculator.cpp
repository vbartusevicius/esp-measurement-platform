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
