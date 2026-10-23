#include <gtest/gtest.h>
#include "AnalogDistancePlugin.h"
#include "HAL.h"
#include "HaDiscovery.h"
#include "LedController.h"
#include "Logger.h"
#include "Storage.h"

static HaDiscoveryContext context()
{
    HaDiscoveryContext ctx;
    ctx.deviceId = "ABC123";
    ctx.stateTopic = "tank/stat/analog_distance";
    ctx.availabilityTopic = "tank/availability";
    return ctx;
}

TEST(HaDiscovery, PublishesRetainedConfigUnderTheObjectIdTopic)
{
    MQTTClient client;
    static const HaEntity entity = {"sensor", "level", "level", "Level", nullptr, "%", nullptr, nullptr, true, false};
    HaDiscovery::publish(client, context(), entity, "Tank");
    ASSERT_EQ(client.published.size(), 1u);
    EXPECT_EQ(client.published[0].topic, "homeassistant/sensor/ABC123/level/config");
    EXPECT_TRUE(client.published[0].retained);
    EXPECT_EQ(client.published[0].qos, 1);
}

TEST(HaDiscovery, EmptyObjectIdKeepsTheLegacyTopic)
{
    MQTTClient client;
    static const HaEntity entity = {"sensor", "", "distance", "Distance", nullptr, nullptr, nullptr, nullptr, false, false};
    HaDiscovery::publish(client, context(), entity, nullptr);
    EXPECT_EQ(client.published[0].topic, "homeassistant/sensor/ABC123/config");
}

TEST(HaDiscovery, MeasurementStateIsNotRetained)
{
    MQTTClient client;
    JsonDocument doc;
    HaDiscovery::publishJson(client, "tank/stat/analog_distance", doc);
    EXPECT_EQ(client.published[0].topic, "tank/stat/analog_distance");
    EXPECT_FALSE(client.published[0].retained);
}

TEST(HaDiscovery, AnalogDistanceTopicsAreStableAndVolumeIsOptional)
{
    HAL hal;
    Storage storage;
    Logger logger;
    storage.begin();
    storage.reset();
    AnalogDistancePlugin plugin;

    MQTTClient withoutVolume;
    plugin.setup(&hal, &storage, &logger, nullptr);
    plugin.publishHomeAssistantAutoconfig(withoutVolume, context());
    std::vector<std::string> topics;
    for (auto& m : withoutVolume.published) topics.push_back(m.topic);
    EXPECT_EQ(topics, (std::vector<std::string>{
        "homeassistant/sensor/ABC123/level/config",
        "homeassistant/sensor/ABC123/depth/config",
        "homeassistant/binary_sensor/ABC123/connected/config"}));

    storage.saveParameter(DistancePluginBase::PARAM_TOTAL_VOLUME, String("3000"));
    MQTTClient withVolume;
    plugin.setup(&hal, &storage, &logger, nullptr);
    plugin.publishHomeAssistantAutoconfig(withVolume, context());
    EXPECT_EQ(withVolume.published.size(), 6u);
    EXPECT_EQ(withVolume.published[2].topic, "homeassistant/sensor/ABC123/volume/config");
}

TEST(LedController, NetworkStatePriority)
{
    using S = LedController::NetState;
    EXPECT_EQ(LedController::netStateFor(true, true, false), S::MQTT);
    EXPECT_EQ(LedController::netStateFor(true, false, true), S::WIFI);
    EXPECT_EQ(LedController::netStateFor(false, false, true), S::PORTAL);
    EXPECT_EQ(LedController::netStateFor(false, true, false), S::OFFLINE);
}
