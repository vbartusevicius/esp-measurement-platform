#include <gtest/gtest.h>
#include <set>
#include <vector>
#include "AnalogDistancePlugin.h"
#include "AnalogVoltagePlugin.h"
#include "HAL.h"
#include "HaDiscovery.h"
#include "Logger.h"
#include "Parameter.h"
#include "PluginRegistry.h"
#include "PulseMeterPlugin.h"
#include "RadiationCounterPlugin.h"
#include "ScopedSettings.h"
#include "SensorHub.h"
#include "Storage.h"
#include "UltrasonicDistancePlugin.h"

class SensorHubTest : public ::testing::Test {
protected:
    HAL hal;
    Storage storage;
    Logger logger;
    PluginRegistry registry;
    AnalogDistancePlugin analog;
    UltrasonicDistancePlugin ultrasonic;
    RadiationCounterPlugin radiation;
    AnalogVoltagePlugin voltage;
    PulseMeterPlugin meter;

    void SetUp() override {
        FakeHAL::currentMillis = 0;
        storage.begin();
        storage.reset();
        for (IPlugin* p : std::vector<IPlugin*>{&analog, &ultrasonic, &radiation, &voltage, &meter}) registry.add(p);
    }
};

TEST_F(SensorHubTest, ParsesTheListInOrderAndDropsUnknownAndRepeatedIds)
{
    auto plugins = SensorHub::parse("pulse_meter, nope,analog_distance,pulse_meter", registry);
    ASSERT_EQ(plugins.size(), 2u);
    EXPECT_EQ(plugins[0], &meter);
    EXPECT_EQ(plugins[1], &analog);
}

TEST_F(SensorHubTest, FallsBackToTheSinglePluginOfOlderSettings)
{
    storage.saveParameter(Parameter::ACTIVE_PLUGIN, String("radiation_counter"));
    auto plugins = SensorHub::enabled(storage, registry);
    ASSERT_EQ(plugins.size(), 1u);
    EXPECT_EQ(plugins[0], &radiation);
}

TEST_F(SensorHubTest, AllFiveSensorsShareNoInputButTwoOnOneInputClash)
{
    EXPECT_EQ(SensorHub::clash({&analog, &ultrasonic, &radiation, &voltage, &meter}), nullptr);
    // a second sensor on IO1/IO2 (here: the same type twice) is refused
    EXPECT_EQ(SensorHub::clash({&ultrasonic, &meter, &ultrasonic}), &ultrasonic);
}

TEST_F(SensorHubTest, PrefixesAreUnique)
{
    std::set<std::string> prefixes;
    for (IPlugin* p : registry.getAll()) prefixes.insert(ScopedSettings::prefixFor(p->getId()).c_str());
    EXPECT_EQ(prefixes.size(), registry.getAll().size());
    EXPECT_STREQ(ScopedSettings::prefixFor("analog_distance").c_str(), "ad.");
}

TEST_F(SensorHubTest, SensorsKeepTheirOwnSettingsAndSchedules)
{
    storage.saveParameter(Parameter::SENSORS, String("analog_distance,radiation_counter"));
    storage.saveParameter("ad.sampling_interval", String("10"));
    SensorHub hub;
    hub.begin(&storage, registry, &hal, &logger, nullptr);
    ASSERT_EQ(hub.size(), 2u);
    EXPECT_EQ(hub.indexOf("radiation_counter"), 1);
    EXPECT_EQ(hub.settings(0).getParameter("sampling_interval", ""), String("10"));
    EXPECT_EQ(hub.settings(1).getParameter("sampling_interval", ""), String(""));   // not the tank's value

    int tank = 0, rad = 0;
    for (unsigned long t = 0; t < 30000; t += 1000) {
        tank += hub.sampleDue(0, t);
        rad += hub.sampleDue(1, t);
    }
    EXPECT_EQ(tank, 3);    // every 10 s
    EXPECT_EQ(rad, 30);    // every 1 s
}

TEST_F(SensorHubTest, EverySensorFullyConfiguredFitsTheSettingsStore)
{
    storage.saveParameter(Parameter::SENSORS, String("analog_distance,ultrasonic_distance,radiation_counter,analog_voltage,pulse_meter"));
    for (const char* k : {Parameter::DEVICE_NAME, Parameter::MQTT_HOST, Parameter::MQTT_USER, Parameter::MQTT_PASS, Parameter::MQTT_DEVICE}) {
        storage.saveParameter(k, String("a-rather-long-value-24ch"));
    }
    storage.saveParameter(Parameter::MQTT_PORT, String("1883"));
    storage.saveParameter(Parameter::RELAY_MODE, String("off_alarm"));
    storage.saveParameter(Parameter::RELAY_SOURCE, String("ultrasonic_distance"));
    for (IPlugin* p : registry.getAll()) {
        ScopedSettings s(&storage, ScopedSettings::prefixFor(p->getId()));
        std::vector<ParameterDef> defs;
        p->getParameterDefs(defs);
        for (const ParameterDef& d : defs) s.saveParameter(d.key, String("12345.678"));
        for (const char* k : {Parameter::LIMIT_LOW, Parameter::LIMIT_HIGH, Parameter::LIMIT_HYSTERESIS,
                              Parameter::LIMIT_LOW_ON, Parameter::LIMIT_HIGH_ON}) s.saveParameter(k, String("123.45"));
    }
    ScopedSettings(&storage, String("pm.")).saveParameter(PulseMeterPlugin::KEY_TOTAL_LITERS, String("1666623.0"));
    ScopedSettings(&storage, String("pm.")).saveParameter(PulseMeterPlugin::KEY_READING_APPLIED, String("1666.623"));
    EXPECT_LE(storage.usedBytes(), Storage::capacity());
    Storage reloaded;
    reloaded.begin();
    EXPECT_EQ(reloaded.getParameter("pm.meter_total_l", ""), String("1666623.0"));   // the last write made it to flash
}

TEST_F(SensorHubTest, HomeAssistantEntitiesArePrefixedPerSensor)
{
    MQTTClient client;
    HaDiscoveryContext ctx;
    ctx.deviceId = "ABC123";
    ctx.stateTopic = "dev/stat/pulse_meter";
    ctx.availabilityTopic = "dev/availability";
    ctx.objectPrefix = "pulse_meter_";
    static const HaEntity total = {"sensor", "total", "total", "Water Meter", nullptr, nullptr, nullptr, nullptr, false, false};
    static const HaEntity legacy = {"sensor", "", "distance", "Distance", nullptr, nullptr, nullptr, nullptr, false, false};
    HaDiscovery::publish(client, ctx, total, nullptr);
    HaDiscovery::publish(client, ctx, legacy, nullptr);
    EXPECT_EQ(client.published[0].topic, "homeassistant/sensor/ABC123/pulse_meter_total/config");
    EXPECT_EQ(client.published[1].topic, "homeassistant/sensor/ABC123/pulse_meter/config");
    EXPECT_NE(client.published[0].payload.find("\"unique_id\":\"ABC123_pulse_meter_total\""), std::string::npos);
}
