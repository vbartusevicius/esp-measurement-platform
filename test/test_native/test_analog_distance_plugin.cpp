#include <gtest/gtest.h>
#include "AnalogDistancePlugin.h"
#include "HAL.h"
#include "Storage.h"
#include "Logger.h"

class MockHal : public HAL {
public:
    int analogValue = 512;
    std::vector<std::pair<uint8_t, uint8_t>> pinModes;

    void pinMode(uint8_t pin, uint8_t mode) override { pinModes.push_back({pin, mode}); }
    int analogRead(uint8_t) override { return analogValue; }
    unsigned long millis() override { return FakeHAL::currentMillis; }
};

class AnalogDistancePluginTest : public ::testing::Test {
protected:
    MockHal hal;
    Storage storage;
    Logger logger;
    AnalogDistancePlugin plugin;

    void SetUp() override {
        storage.begin();
        storage.reset();
        FakeHAL::currentMillis = 0;

        String range = "5";
        storage.saveParameter(AnalogDistancePlugin::PARAM_SENSOR_RANGE, range);
        String empty = "50";   // 0.5 m
        storage.saveParameter(DistancePluginBase::PARAM_DISTANCE_EMPTY, empty);
        String full = "350";   // 3.5 m
        storage.saveParameter(DistancePluginBase::PARAM_DISTANCE_FULL, full);
    }
};

TEST_F(AnalogDistancePluginTest, SetupConfiguresAnalogPin)
{
    plugin.setup(&hal, &storage, &logger, nullptr);
    ASSERT_EQ(hal.pinModes.size(), 1u);
    EXPECT_EQ(hal.pinModes[0].first, A0);
    EXPECT_EQ(hal.pinModes[0].second, INPUT);
}

TEST_F(AnalogDistancePluginTest, LoopComputesRelativeAndAbsolute)
{
    // raw=512 -> 1.65V -> ~12mA -> ~2.5m on a 5m-range sensor
    plugin.setup(&hal, &storage, &logger, nullptr);
    plugin.loop();

    std::vector<StatEntry> stats;
    plugin.getStats(stats);
    ASSERT_GE(stats.size(), 4u);

    // level = (2.50 - 0.5) / (3.5 - 0.5) = 0.667
    EXPECT_NEAR(stats[0].numericValue, 0.6675f, 0.01f);
    // depth = level * 3.5 = 2.34 m
    EXPECT_NEAR(stats[1].numericValue, 2.3362f, 0.01f);
}

TEST_F(AnalogDistancePluginTest, SensorDisconnectedBelowFaultCurrent)
{
    // raw=0 -> 0V -> 4.0mA < 4.17mA fault threshold
    hal.analogValue = 0;
    plugin.setup(&hal, &storage, &logger, nullptr);
    plugin.loop();

    std::vector<StatEntry> stats;
    plugin.getStats(stats);

    bool foundDisconnected = false;
    for (auto& e : stats) {
        if (strcmp(e.label, "Sensor") == 0) {
            foundDisconnected = strcmp(e.value.c_str(), "Disconnected") == 0;
        }
    }
    EXPECT_TRUE(foundDisconnected);
}

TEST_F(AnalogDistancePluginTest, FlowRateReportedWhenVolumeConfigured)
{
    String volume = "1000";
    storage.saveParameter(DistancePluginBase::PARAM_TOTAL_VOLUME, volume);

    plugin.setup(&hal, &storage, &logger, nullptr);

    plugin.loop();  // inflow rises over time
    FakeHAL::currentMillis = 10000;
    hal.analogValue = 600;
    plugin.loop();

    std::vector<StatEntry> stats;
    plugin.getStats(stats);
    bool foundFlow = false;
    for (auto& e : stats) {
        if (strcmp(e.label, "Flow Rate") == 0) foundFlow = true;
    }
    EXPECT_TRUE(foundFlow);
}

TEST_F(AnalogDistancePluginTest, FlowRateHiddenWithoutVolume)
{
    plugin.setup(&hal, &storage, &logger, nullptr);
    plugin.loop();

    std::vector<StatEntry> stats;
    plugin.getStats(stats);
    for (auto& e : stats) {
        EXPECT_STRNE(e.label, "Flow Rate");
        EXPECT_STRNE(e.label, "Volume");
        EXPECT_STRNE(e.label, "Usage 24h");
    }
    EXPECT_EQ(stats.size(), 5u);  // Level, Depth, Distance, Raw, Sensor
}

TEST_F(AnalogDistancePluginTest, ExposesCapabilities)
{
    EXPECT_NE(plugin.mqtt(), nullptr);
    EXPECT_NE(plugin.display(), nullptr);
    EXPECT_EQ(plugin.display()->getDisplayPageCount(), 1);
}
