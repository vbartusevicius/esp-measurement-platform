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

