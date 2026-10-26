#ifndef HA_DISCOVERY_H
#define HA_DISCOVERY_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <MQTT.h>

struct HaDiscoveryContext {
    String deviceId;
    String stateTopic;
    String availabilityTopic;
    String deviceName;   // user-configured display name; empty = plugin default
    String objectPrefix; // "<plugin id>_" for sensor entities, so sensors side by side never collide

    const char* nameOr(const char* fallback) const {
        return deviceName.isEmpty() ? fallback : deviceName.c_str();
    }
};

// One Home Assistant entity. Topic: homeassistant/<component>/<device>/<prefix><objectId>/config
// (just <prefix> without its "_" when objectId is empty); unique_id = <device>_<prefix><uniqueSuffix>.
// Keep both stable so existing HA entities keep their history.
struct HaEntity {
    const char* component;        // sensor | binary_sensor | switch
    const char* objectId;
    const char* uniqueSuffix;
    const char* name;
    const char* valueTemplate;
    const char* unit;
    const char* deviceClass;
    const char* icon;
    bool measurement;             // state_class: measurement (numeric states only)
    bool diagnostic;              // entity_category: diagnostic
};

namespace HaDiscovery
{
    // MQTT client read/write buffer. arduino-mqtt defaults to 128 bytes and silently refuses
    // larger messages; a discovery config is several hundred (test_all_sensors checks the largest).
    constexpr size_t MQTT_BUFFER_SIZE = 1024;

    // Publishes the retained discovery config. The state topic defaults to
    // ctx.stateTopic; `extra` may add or override fields (command_topic, ...).
    // deviceName nullptr = don't rename the HA device (it merges by identifier).
    void publish(MQTTClient& client, const HaDiscoveryContext& ctx, const HaEntity& entity,
                 const char* deviceName, void (*extra)(JsonDocument&, const HaDiscoveryContext&) = nullptr);

    // Publishes a JSON payload (measurement state, not retained).
    void publishJson(MQTTClient& client, const String& topic, JsonDocument& doc);
}

#endif
