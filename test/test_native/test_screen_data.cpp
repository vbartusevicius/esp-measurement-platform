#include <gtest/gtest.h>
#include <cmath>
#include "TrendBuffer.h"
#include "RollingExtremes.h"
#include "LimitMonitor.h"
#include "EventLog.h"
#include "AnalogVoltageConverter.h"

// --- TrendBuffer ---

TEST(TrendBuffer, AveragesSamplesPerBucketAndShowsTheRunningBucket)
{
    TrendBuffer trend(1000);
    trend.add(10.0f, 0);
    trend.add(20.0f, 500);
    trend.add(40.0f, 1000);   // closes the first bucket (avg 15)
    auto values = trend.values();
    ASSERT_EQ(values.size(), 2u);
    EXPECT_FLOAT_EQ(values[0], 15.0f);
    EXPECT_FLOAT_EQ(values[1], 40.0f);
}

TEST(TrendBuffer, KeepsTheNewestCapacityPointsOldestFirst)
{
    TrendBuffer trend(1);
    for (int i = 0; i < 100; i++) trend.add((float)i, (unsigned long)i);
    auto values = trend.values();
    ASSERT_EQ(values.size(), TrendBuffer::CAPACITY);
    EXPECT_FLOAT_EQ(values.back(), 99.0f);
    EXPECT_FLOAT_EQ(values.front(), (float)(100 - TrendBuffer::CAPACITY));
}

TEST(TrendBuffer, EmptyUntilTheFirstSample)
{
    TrendBuffer trend;
    EXPECT_TRUE(trend.values().empty());
}

// --- RollingExtremes ---

TEST(RollingExtremes, TracksLowAndHighWithinTheWindow)
{
    RollingExtremes ext(1000);
    EXPECT_FALSE(ext.valid());
    ext.update(50.0f, 0);
    ext.update(20.0f, 1500);
    ext.update(80.0f, 2500);
    EXPECT_TRUE(ext.valid());
    EXPECT_FLOAT_EQ(ext.min(), 20.0f);
    EXPECT_FLOAT_EQ(ext.max(), 80.0f);
}

TEST(RollingExtremes, ForgetsBucketsOlderThanTheWindow)
{
    RollingExtremes ext(1000);
    ext.update(5.0f, 0);                    // slot 0
    for (int s = 1; s <= 24; s++) ext.update(50.0f, s * 1000UL);   // slots 1..24
    EXPECT_FLOAT_EQ(ext.min(), 50.0f);      // slot 0 is now 24 slots old
}

// --- LimitMonitor ---

TEST(LimitMonitor, EntersLowAlarmAndClearsWithHysteresis)
{
    LimitMonitor lim;
    lim.configure(20.0f, 95.0f, 5.0f, LimitMonitor::RelayMode::ON_ALARM);
    EXPECT_FALSE(lim.update(50.0f, true));
    EXPECT_TRUE(lim.update(18.0f, true));
    EXPECT_EQ(lim.state(), LimitMonitor::State::BELOW);
    EXPECT_FLOAT_EQ(lim.activeLimit(), 20.0f);
    EXPECT_FALSE(lim.update(22.0f, true));  // inside hysteresis band
    EXPECT_TRUE(lim.update(25.0f, true));
    EXPECT_EQ(lim.state(), LimitMonitor::State::NORMAL);
    EXPECT_EQ(lim.trips(), 1u);
}

TEST(LimitMonitor, HighAlarmDrivesTheRelayRule)
{
    LimitMonitor lim;
    lim.configure(NAN, 3.0f, 0.2f, LimitMonitor::RelayMode::OFF_ALARM);
    bool on = false;
    lim.update(2.0f, true);
    ASSERT_TRUE(lim.relayDemand(on));
    EXPECT_TRUE(on);                        // OFF_ALARM: energised while normal
    lim.update(3.5f, true);
    EXPECT_EQ(lim.state(), LimitMonitor::State::ABOVE);
    lim.relayDemand(on);
    EXPECT_FALSE(on);
}

TEST(LimitMonitor, InvalidReadingsHoldTheState)
{
    LimitMonitor lim;
    lim.configure(20.0f, NAN, 0.0f, LimitMonitor::RelayMode::MANUAL);
    lim.update(10.0f, true);
    EXPECT_FALSE(lim.update(50.0f, false));
    EXPECT_FALSE(lim.update(NAN, true));
    EXPECT_TRUE(lim.alarm());
    bool on = false;
    EXPECT_FALSE(lim.relayDemand(on));      // manual: no automatic relay control
}

TEST(LimitMonitor, AcknowledgeHidesTheAlertUntilTheNextTransition)
{
    LimitMonitor lim;
    lim.configure(20.0f, 80.0f, 0.0f, LimitMonitor::RelayMode::MANUAL);
    lim.update(10.0f, true);
    EXPECT_TRUE(lim.alertPending());
    lim.acknowledge();
    EXPECT_FALSE(lim.alertPending());
    EXPECT_TRUE(lim.alarm());
    lim.update(90.0f, true);                // straight across into the high alarm
    EXPECT_EQ(lim.state(), LimitMonitor::State::ABOVE);
    EXPECT_TRUE(lim.alertPending());
}

TEST(LimitMonitor, ParsesRelayModes)
{
    EXPECT_EQ(LimitMonitor::parseMode("on_alarm"), LimitMonitor::RelayMode::ON_ALARM);
    EXPECT_EQ(LimitMonitor::parseMode("off_alarm"), LimitMonitor::RelayMode::OFF_ALARM);
    EXPECT_EQ(LimitMonitor::parseMode("bogus"), LimitMonitor::RelayMode::MANUAL);
    EXPECT_EQ(LimitMonitor::parseMode(nullptr), LimitMonitor::RelayMode::MANUAL);
}

// --- EventLog ---

TEST(EventLog, StoresUppercaseTruncatedEntriesNewestFirst)
{
    EventLog log;
    log.add("system boot", "fw 1.2.3", 1000);
    log.add("MQTT ONLINE", "192.168.0.10.extra-long", 5000);
    ASSERT_EQ(log.size(), 2u);
    EXPECT_STREQ(log.newest(0).title, "MQTT ONLINE");
    EXPECT_STREQ(log.newest(0).detail, "192.168.0.10.EXT");   // 16 chars: the OLED width
    EXPECT_EQ(log.newest(0).uptimeSec, 5u);
    EXPECT_STREQ(log.newest(1).title, "SYSTEM BOOT");
}

TEST(EventLog, WrapsAtCapacity)
{
    EventLog log;
    for (int i = 0; i < 20; i++) log.add(std::to_string(i).c_str(), "", i * 1000UL);
    EXPECT_EQ(log.size(), EventLog::CAPACITY);
    EXPECT_EQ(log.total(), 20u);
    EXPECT_STREQ(log.newest(0).title, "19");
    EXPECT_STREQ(log.newest(EventLog::CAPACITY - 1).title, "4");
}

// --- AnalogVoltageConverter ---

TEST(AnalogVoltageConverter, AppliesTheBoardDivider)
{
    // 10 V on J2.5 -> 3.125 V at the ADC through 22k/10k
    EXPECT_NEAR(AnalogVoltageConverter::pinToInputVolts(3125, 3.2f), 10.0f, 1e-3);
}

TEST(AnalogVoltageConverter, ScalesAndClampsALiveZeroPressureSensor)
{
    EXPECT_NEAR(AnalogVoltageConverter::scale(0.5f, 0.5f, 4.5f, 0.0f, 10.0f), 0.0f, 1e-4);
    EXPECT_NEAR(AnalogVoltageConverter::scale(2.5f, 0.5f, 4.5f, 0.0f, 10.0f), 5.0f, 1e-4);
    EXPECT_NEAR(AnalogVoltageConverter::scale(4.9f, 0.5f, 4.5f, 0.0f, 10.0f), 10.0f, 1e-4);
    EXPECT_NEAR(AnalogVoltageConverter::scale(0.1f, 0.5f, 4.5f, 0.0f, 10.0f), 0.0f, 1e-4);
}

TEST(AnalogVoltageConverter, DetectsOpenLiveZeroSensorButNotZeroVolts0To10)
{
    EXPECT_FALSE(AnalogVoltageConverter::isConnected(0.02f, 0.5f, 4.5f));
    EXPECT_TRUE(AnalogVoltageConverter::isConnected(0.45f, 0.5f, 4.5f));
    EXPECT_FALSE(AnalogVoltageConverter::isConnected(5.2f, 0.5f, 4.5f));
    EXPECT_TRUE(AnalogVoltageConverter::isConnected(0.0f, 0.0f, 10.0f));
    EXPECT_FALSE(AnalogVoltageConverter::isConnected(11.5f, 0.0f, 10.0f));
}

TEST(TrendBuffer, CustomCapacityFor24hHistory)
{
    TrendBuffer history(900000UL, 96);
    for (unsigned long i = 0; i < 200; i++) history.add((float)i, i * 900000UL);
    auto values = history.values();
    ASSERT_EQ(values.size(), 96u);
    EXPECT_FLOAT_EQ(values.back(), 199.0f);
}
