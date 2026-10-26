#include <gtest/gtest.h>
#include <ArduinoJson.h>
#include <string>
#include <vector>
#include "HAL.h"
#include "HaDiscovery.h"
#include "Logger.h"
#include "Storage.h"
#include "PulseMeterPlugin.h"

namespace
{
    class ClockHal : public HAL {
    public:
        unsigned long millis() override { return FakeHAL::currentMillis; }
    };

    constexpr unsigned long SEC = 1000UL;
    constexpr unsigned long MIN = 60UL * SEC;
    constexpr unsigned long HOUR = 60UL * MIN;
}

class PulseMeterPluginTest : public ::testing::Test {
protected:
    ClockHal hal;
    Storage storage;
    Logger logger;
    PulseMeterPlugin plugin;

    void SetUp() override
    {
        FakeHAL::currentMillis = 0;
        storage.begin();
        storage.reset();
    }

    void start(const char* litersPerPulse = "1")
    {
        storage.saveParameter(PulseMeterPlugin::PARAM_LITERS_PER_PULSE, String(litersPerPulse));
        plugin.setup(&hal, &storage, &logger, nullptr);
    }

    // A pulse at `at`, then the 1 s sampling loop up to `at`.
    void pulseAt(unsigned long at)
    {
        FakeHAL::currentMillis = at;
        plugin.onPulse(at);
        plugin.loop();
    }

    void runUntil(unsigned long at)
    {
        FakeHAL::currentMillis = at;
        plugin.loop();
    }
};

TEST_F(PulseMeterPluginTest, EveryPulseAddsTheLitresPerPulse)
{
    start("10");
    for (int i = 1; i <= 5; i++) pulseAt(i * MIN);
    EXPECT_DOUBLE_EQ(plugin.totalLiters(), 50.0);
    EXPECT_NEAR(plugin.flowLitersPerMinute(), 10.0f, 0.01f);   // 10 L every minute
}

TEST_F(PulseMeterPluginTest, ContactNoiseWithinTheMinimumGapCountsOnce)
{
    start();
    pulseAt(10 * SEC);
    pulseAt(10 * SEC + 10);    // 10 ms later: bounce
    pulseAt(10 * SEC + 49);
    pulseAt(10 * SEC + 60);    // >= 50 ms after the counted edge: a real pulse
    EXPECT_DOUBLE_EQ(plugin.totalLiters(), 2.0);
}

TEST_F(PulseMeterPluginTest, MeterReadingSetsTheRegisterOnce)
{
    storage.saveParameter(PulseMeterPlugin::PARAM_METER_READING, String("1666.623"));
    start();
    EXPECT_NEAR(plugin.totalLiters(), 1666623.0, 0.01);
    pulseAt(MIN);
    plugin.persist();

    PulseMeterPlugin restarted;   // same reading saved: keep counting from the stored total
    restarted.setup(&hal, &storage, &logger, nullptr);
    EXPECT_NEAR(restarted.totalLiters(), 1666624.0, 0.01);

    storage.saveParameter(PulseMeterPlugin::PARAM_METER_READING, String("1700"));   // new reading: replaces it
    PulseMeterPlugin corrected;
    corrected.setup(&hal, &storage, &logger, nullptr);
    EXPECT_NEAR(corrected.totalLiters(), 1700000.0, 0.01);
}

TEST_F(PulseMeterPluginTest, TotalIsWrittenToFlashAtMostEveryTenMinutes)
{
    start();
    pulseAt(MIN);
    EXPECT_EQ(storage.getParameter(PulseMeterPlugin::KEY_TOTAL_LITERS, ""), String(""));   // not written yet
    runUntil(PulseMeterPlugin::PERSIST_INTERVAL_MS + SEC);
    EXPECT_EQ(storage.getParameter(PulseMeterPlugin::KEY_TOTAL_LITERS, ""), String("1.0"));
}

TEST_F(PulseMeterPluginTest, FlowDecaysWhenPulsesStopAndEndsAfterTenMinutes)
{
    start("10");
    pulseAt(1 * MIN);
    pulseAt(2 * MIN);
    runUntil(4 * MIN);            // 2 min without a pulse: at most 10 L / 2 min
    EXPECT_NEAR(plugin.flowLitersPerMinute(), 5.0f, 0.01f);
    runUntil(13 * MIN);
    EXPECT_FLOAT_EQ(plugin.flowLitersPerMinute(), 0.0f);
}

TEST_F(PulseMeterPluginTest, FlowThatNeverStopsForAnHourIsALeak)
{
    storage.saveParameter(PulseMeterPlugin::PARAM_LEAK_HOURS, String("24"));
    start();
    for (unsigned long t = 30 * MIN; t <= 25 * HOUR; t += 30 * MIN) pulseAt(t);
    EXPECT_GE(plugin.continuousFlowHours(), 24);
    EXPECT_TRUE(plugin.leak());
    EXPECT_NEAR(plugin.usage24hLiters(), 48.0f, 2.0f);

    runUntil(27 * HOUR);          // a whole quiet hour ends it
    EXPECT_EQ(plugin.continuousFlowHours(), 0);
    EXPECT_FALSE(plugin.leak());
}

TEST_F(PulseMeterPluginTest, ChartHasFifteenMinuteBarsOfLitres)
{
    start();
    pulseAt(1 * MIN);
    pulseAt(2 * MIN);
    pulseAt(20 * MIN);
    std::vector<float> points;
    int span = 0;
    ASSERT_TRUE(plugin.getChartData(points, span));
    EXPECT_EQ(span, 900);
    ASSERT_EQ(points.size(), 2u);
    EXPECT_FLOAT_EQ(points[0], 2.0f);
    EXPECT_FLOAT_EQ(points[1], 1.0f);
}

TEST_F(PulseMeterPluginTest, ScreenShowsFlowAndTheRegister)
{
    storage.saveParameter(PulseMeterPlugin::PARAM_METER_READING, String("12.5"));
    start("10");
    pulseAt(MIN);
    pulseAt(2 * MIN);
    ScreenModel screen;
    ASSERT_TRUE(plugin.getScreen(screen));
    EXPECT_STREQ(screen.kind, "meter");
    EXPECT_STREQ(screen.title, "WATR");
    EXPECT_STREQ(screen.unit, "L/min");
    EXPECT_NEAR(screen.value, 10.0f, 0.01f);
    EXPECT_EQ(screen.raw, String("12.520m3"));
}

TEST_F(PulseMeterPluginTest, HomeAssistantGetsAWaterTotalForTheEnergyDashboard)
{
    start();
    MQTTClient client;
    HaDiscoveryContext ctx;
    ctx.deviceId = "ABC123";
    ctx.stateTopic = "house/stat/pulse_meter";
    ctx.availabilityTopic = "house/availability";
    plugin.publishHomeAssistantAutoconfig(client, ctx);

    std::vector<std::string> topics;
    for (auto& m : client.published) topics.push_back(m.topic);
    EXPECT_EQ(topics, (std::vector<std::string>{
                          "homeassistant/sensor/ABC123/total/config",
                          "homeassistant/sensor/ABC123/flow/config",
                          "homeassistant/sensor/ABC123/usage_24h/config",
                          "homeassistant/binary_sensor/ABC123/leak/config",
                      }));
    JsonDocument total;
    ASSERT_FALSE(deserializeJson(total, client.published[0].payload));
    EXPECT_STREQ(total["device_class"], "water");
    EXPECT_STREQ(total["state_class"], "total_increasing");
    EXPECT_STREQ(total["unit_of_measurement"], "m\xC2\xB3");
}

TEST_F(PulseMeterPluginTest, GasMediumGivesHomeAssistantAGasTotal)
{
    storage.saveParameter(PulseMeterPlugin::PARAM_MEDIUM, String("gas"));
    start("10");
    MQTTClient client;
    HaDiscoveryContext ctx;
    ctx.deviceId = "ABC123";
    ctx.stateTopic = "house/stat/pulse_meter";
    ctx.availabilityTopic = "house/availability";
    plugin.publishHomeAssistantAutoconfig(client, ctx);
    JsonDocument total;
    ASSERT_FALSE(deserializeJson(total, client.published[0].payload));
    EXPECT_STREQ(total["device_class"], "gas");
    EXPECT_STREQ(total["name"], "Gas Meter");
    ScreenModel screen;
    plugin.getScreen(screen);
    EXPECT_STREQ(screen.title, "GAS");
}

TEST_F(PulseMeterPluginTest, OledDiagnosticsShowTheLastPulseAgeAndThePeakFlow)
{
    start("1");
    ScreenModel before;
    plugin.getScreen(before);
    ASSERT_EQ(before.details.size(), 2u);
    EXPECT_STREQ(before.details[0].label, "LAST");
    EXPECT_EQ(before.details[0].value, String("--"));   // nothing seen yet: check the reader

    for (int i = 1; i <= 10; i++) pulseAt(i * 6000UL);   // 1 L every 6 s = 10 L/min
    runUntil(60000UL + 95000UL);
    ScreenModel after;
    plugin.getScreen(after);
    EXPECT_EQ(after.details[0].value, String("1m"));
    EXPECT_STREQ(after.details[1].label, "MAX");
    EXPECT_TRUE(after.details[1].value.endsWith("L/m"));
    EXPECT_NEAR(after.details[1].value.toFloat(), 10.0f, 0.6f);
    EXPECT_EQ(after.lines[0].value, String("0.0m3"));
}
