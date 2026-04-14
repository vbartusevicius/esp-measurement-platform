#include <gtest/gtest.h>
#include "AnalogDistanceCalculator.h"
#include "UltrasonicDistanceCalculator.h"

// ====== Analog distance static methods ======

TEST(AnalogDistanceCalculator, GetRelativeReturnZeroBelowEmpty)
{
    EXPECT_FLOAT_EQ(AnalogDistanceCalculator::getRelative(0.05, 0.10, 1.00), 0.0f);
}

TEST(AnalogDistanceCalculator, GetRelativeReturnOneBeyondFull)
{
    EXPECT_FLOAT_EQ(AnalogDistanceCalculator::getRelative(1.50, 0.10, 1.00), 1.0f);
}

TEST(AnalogDistanceCalculator, GetRelativeMidpoint)
{
    float result = AnalogDistanceCalculator::getRelative(0.55, 0.10, 1.00);
    EXPECT_NEAR(result, 0.5f, 0.01f);
}

TEST(AnalogDistanceCalculator, GetRelativeAtEmptyBoundary)
{
    EXPECT_FLOAT_EQ(AnalogDistanceCalculator::getRelative(0.10, 0.10, 1.00), 0.0f);
}

TEST(AnalogDistanceCalculator, GetRelativeAtFullBoundary)
{
    EXPECT_FLOAT_EQ(AnalogDistanceCalculator::getRelative(1.00, 0.10, 1.00), 1.0f);
}

TEST(AnalogDistanceCalculator, GetAbsoluteAtZeroRelative)
{
    float result = AnalogDistanceCalculator::getAbsolute(0.05, 0.10, 1.00);
    EXPECT_FLOAT_EQ(result, 0.0f);
}

TEST(AnalogDistanceCalculator, GetAbsoluteAtFullRelative)
{
    float result = AnalogDistanceCalculator::getAbsolute(1.00, 0.10, 1.00);
    EXPECT_FLOAT_EQ(result, 1.00f);
}

TEST(AnalogDistanceCalculator, GetAbsoluteMidpoint)
{
    float result = AnalogDistanceCalculator::getAbsolute(0.55, 0.10, 1.00);
    EXPECT_NEAR(result, 0.5f, 0.01f);
}

// ====== Ultrasonic distance static methods ======

TEST(UltrasonicDistanceCalculator, AbsoluteBasic)
{
    EXPECT_FLOAT_EQ(UltrasonicDistanceCalculator::getAbsolute(0.5, 2.0), 1.5f);
}

TEST(UltrasonicDistanceCalculator, AbsoluteClampedToZero)
{
    EXPECT_FLOAT_EQ(UltrasonicDistanceCalculator::getAbsolute(3.0, 2.0), 0.0f);
}

TEST(UltrasonicDistanceCalculator, RelativeBasic)
{
    // emptyDist=2.0m, fullDist=0.2m, distance=1.1m
    // absolute = 2.0 - 1.1 = 0.9
    // denominator = 2.0 - 0.2 = 1.8
    // relative = 0.9 / 1.8 = 0.5
    float result = UltrasonicDistanceCalculator::getRelative(1.1, 2.0, 0.2);
    EXPECT_NEAR(result, 0.5f, 0.01f);
}

TEST(UltrasonicDistanceCalculator, RelativeZeroDenominator)
{
    EXPECT_FLOAT_EQ(UltrasonicDistanceCalculator::getRelative(1.0, 2.0, 2.0), 0.0f);
}

// ====== Aggregation (shared logic, tested via AnalogDistanceCalculator) ======

class AnalogDistCalcAggregateTest : public ::testing::Test {
protected:
    AnalogDistanceCalculator calc;
    void SetUp() override { calc.reset(); }
};

TEST_F(AnalogDistCalcAggregateTest, SingleValueReturnsItself)
{
    float avg = calc.aggregate(1.5, 10, 15);
    EXPECT_FLOAT_EQ(avg, 1.5f);
}

TEST_F(AnalogDistCalcAggregateTest, AveragesMultipleValues)
{
    calc.aggregate(1.0, 10, 100);
    float avg = calc.aggregate(2.0, 10, 100);
    EXPECT_NEAR(avg, 1.5f, 0.01f);
}

TEST_F(AnalogDistCalcAggregateTest, RespectsWindowSize)
{
    for (int i = 1; i <= 3; i++) {
        calc.aggregate((float)i, 3, 100);
    }
    // buffer: [1, 2, 3], avg = 2.0
    EXPECT_NEAR(calc.calculateAverage(), 2.0f, 0.01f);

    // Adding 4th value with window=3 should drop 1
    calc.aggregate(4.0, 3, 100);
    // buffer: [2, 3, 4], avg = 3.0
    EXPECT_NEAR(calc.calculateAverage(), 3.0f, 0.01f);
}

TEST_F(AnalogDistCalcAggregateTest, RejectsZeroValue)
{
    calc.aggregate(1.0, 10, 15);
    calc.aggregate(0.0, 10, 15);
    // Zero value should be rejected (round(0 * 100) == 0)
    EXPECT_EQ(calc.getBuffer().size(), 1u);
}

TEST_F(AnalogDistCalcAggregateTest, RejectsLargeDelta)
{
    calc.aggregate(1.0, 10, 15);
    // Jump from 1.0 to 10.0 — delta=9.0, threshold=10.0*(15/100)=1.5 — 1.5 < 9.0 → reject
    calc.aggregate(10.0, 10, 15);
    EXPECT_EQ(calc.getBuffer().size(), 1u);
}

TEST_F(AnalogDistCalcAggregateTest, EmptyBufferReturnsZero)
{
    EXPECT_FLOAT_EQ(calc.calculateAverage(), 0.0f);
}

TEST_F(AnalogDistCalcAggregateTest, ResetClearsBuffer)
{
    calc.aggregate(1.0, 10, 15);
    calc.reset();
    EXPECT_EQ(calc.getBuffer().size(), 0u);
    EXPECT_FLOAT_EQ(calc.calculateAverage(), 0.0f);
}
