#include <gtest/gtest.h>
#include "AnalogDistancePlugin.h"
#include "Board.h"
#include "HAL.h"
#include "Storage.h"
#include "Logger.h"

class MockHal : public HAL {
public:
    int millivolts = 1440;   // 12 mA across the 120R shunt
    std::vector<std::pair<uint8_t, uint8_t>> pinModes;

    void pinMode(uint8_t pin, uint8_t mode) override { pinModes.push_back({pin, mode}); }
    int analogReadMilliVolts(uint8_t) override { return millivolts; }
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
    EXPECT_EQ(hal.pinModes[0].first, Board::MA_PIN);
    EXPECT_EQ(hal.pinModes[0].second, INPUT);
}

TEST_F(AnalogDistancePluginTest, LoopComputesRelativeAndAbsolute)
{
    // 1440 mV / 120R = 12 mA -> 2.5 m on a 5 m-range sensor
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
    // open loop: 0 mV -> 0 mA < 3.6 mA NAMUR fault limit
    hal.millivolts = 0;
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
    hal.millivolts = 1606;   // 13.4 mA
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
    ScreenModel screen;
    EXPECT_TRUE(plugin.getScreen(screen));   // drawn on the OLED and in the web UI
}

TEST_F(AnalogDistancePluginTest, PublishIntervalDefaultsToSamplingInterval)
{
    String interval = "20";
    storage.saveParameter(DistancePluginBase::PARAM_SAMPLING_INTERVAL, interval);
    plugin.setup(&hal, &storage, &logger, nullptr);

    EXPECT_EQ(plugin.getSamplingInterval(), 20);
    EXPECT_EQ(plugin.getPublishInterval(), 20);
}

TEST_F(AnalogDistancePluginTest, ScreenModelMatchesStatsAndCarriesTrendAndSignal)
{
    plugin.setup(&hal, &storage, &logger, nullptr);
    plugin.loop();
    FakeHAL::currentMillis = 61000;
    plugin.loop();

    ScreenModel screen;
    ASSERT_TRUE(plugin.getScreen(screen));
    EXPECT_STREQ(screen.title, "TANK");
    EXPECT_STREQ(screen.unit, "%");
    EXPECT_TRUE(screen.valid);
    EXPECT_NEAR(screen.value, 66.75f, 1.0f);
    EXPECT_EQ(screen.trend.size(), 2u);             // one closed 1-min bucket + running bucket
    EXPECT_NEAR(screen.low24, screen.value, 0.01f);
    EXPECT_NEAR(screen.high24, screen.value, 0.01f);
    EXPECT_STREQ(screen.signal.c_str(), "12.0mA");
    ASSERT_EQ(screen.lines.size(), 2u);
    EXPECT_STREQ(screen.lines[0].label, "DEP");
}

TEST_F(AnalogDistancePluginTest, ScreenModelShowsVolumeAndFlowWhenConfigured)
{
    storage.saveParameter(DistancePluginBase::PARAM_TOTAL_VOLUME, String("1000"));
    plugin.setup(&hal, &storage, &logger, nullptr);
    plugin.loop();

    ScreenModel screen;
    plugin.getScreen(screen);
    ASSERT_EQ(screen.lines.size(), 2u);
    EXPECT_STREQ(screen.lines[0].label, "VOL");
    EXPECT_STREQ(screen.lines[1].label, "FLW");
}

TEST_F(AnalogDistancePluginTest, FaultedSensorGivesAnInvalidScreenValue)
{
    hal.millivolts = 0;
    plugin.setup(&hal, &storage, &logger, nullptr);
    plugin.loop();

    ScreenModel screen;
    plugin.getScreen(screen);
    EXPECT_FALSE(screen.valid);
    EXPECT_FALSE(screen.sensorOk);
    EXPECT_TRUE(screen.trend.empty());
}

TEST_F(AnalogDistancePluginTest, WebContractHasKindStatKeysAnd24hHistory)
{
    storage.saveParameter(DistancePluginBase::PARAM_TOTAL_VOLUME, String("3000"));
    plugin.setup(&hal, &storage, &logger, nullptr);
    plugin.loop();
    FakeHAL::currentMillis = 900000;
    plugin.loop();

    ScreenModel screen;
    plugin.getScreen(screen);
    EXPECT_STREQ(screen.kind, "level");

    std::vector<StatEntry> stats;
    plugin.getStats(stats);
    bool capacity = false, flow = false;
    for (auto& e : stats) {
        EXPECT_STRNE(e.key, "");
        if (strcmp(e.key, "capacity") == 0) { capacity = true; EXPECT_FLOAT_EQ(e.numericValue, 3000.0f); }
        if (strcmp(e.key, "flow_rate") == 0) flow = true;
    }
    EXPECT_TRUE(capacity);
    EXPECT_TRUE(flow);

    std::vector<float> points;
    int span = 0;
    ASSERT_TRUE(plugin.getChartData(points, span));
    EXPECT_EQ(span, 900);
    EXPECT_EQ(points.size(), 2u);
}
