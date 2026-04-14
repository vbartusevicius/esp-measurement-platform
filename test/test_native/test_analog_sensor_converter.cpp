#include <gtest/gtest.h>
#include "AnalogSensorConverter.h"

// Constants matching AnalogDistancePlugin
static constexpr float VREF = 3.3f;
static constexpr float MIN_MA = 4.0f;
static constexpr float MAX_MA = 20.0f;
static constexpr float FAULT_MA = 4.17f;

// --- voltageToCurrentMA ---

TEST(AnalogSensorConverter, ZeroVoltageReturnsMinCurrent)
{
    float current = AnalogSensorConverter::voltageToCurrentMA(0.0, VREF, MIN_MA, MAX_MA);
    EXPECT_FLOAT_EQ(current, MIN_MA);
}

TEST(AnalogSensorConverter, MaxVoltageReturnsMaxCurrent)
{
    float current = AnalogSensorConverter::voltageToCurrentMA(VREF, VREF, MIN_MA, MAX_MA);
    EXPECT_FLOAT_EQ(current, MAX_MA);
}

TEST(AnalogSensorConverter, MidVoltageReturnsMidCurrent)
{
    float current = AnalogSensorConverter::voltageToCurrentMA(VREF / 2.0f, VREF, MIN_MA, MAX_MA);
    float expected = MIN_MA + (MAX_MA - MIN_MA) / 2.0f;
    EXPECT_FLOAT_EQ(current, expected);
}

// --- currentToDistance ---

TEST(AnalogSensorConverter, MinCurrentReturnsZeroDistance)
{
    float dist = AnalogSensorConverter::currentToDistance(MIN_MA, MIN_MA, MAX_MA, 5.0);
    EXPECT_FLOAT_EQ(dist, 0.0f);
}

TEST(AnalogSensorConverter, MaxCurrentReturnsFullRange)
{
    float dist = AnalogSensorConverter::currentToDistance(MAX_MA, MIN_MA, MAX_MA, 5.0);
    EXPECT_FLOAT_EQ(dist, 5.0f);
}

TEST(AnalogSensorConverter, MidCurrentReturnsMidRange)
{
    float midCurrent = (MIN_MA + MAX_MA) / 2.0f;
    float dist = AnalogSensorConverter::currentToDistance(midCurrent, MIN_MA, MAX_MA, 5.0);
    EXPECT_NEAR(dist, 2.5f, 0.01f);
}

TEST(AnalogSensorConverter, DifferentSensorRange)
{
    float dist = AnalogSensorConverter::currentToDistance(MAX_MA, MIN_MA, MAX_MA, 10.0);
    EXPECT_FLOAT_EQ(dist, 10.0f);
}

// --- isSensorConnected ---

TEST(AnalogSensorConverter, ConnectedAboveFaultThreshold)
{
    EXPECT_TRUE(AnalogSensorConverter::isSensorConnected(5.0, FAULT_MA));
}

TEST(AnalogSensorConverter, DisconnectedBelowFaultThreshold)
{
    EXPECT_FALSE(AnalogSensorConverter::isSensorConnected(4.0, FAULT_MA));
}

TEST(AnalogSensorConverter, ConnectedExactlyAtFaultThreshold)
{
    EXPECT_TRUE(AnalogSensorConverter::isSensorConnected(FAULT_MA, FAULT_MA));
}
