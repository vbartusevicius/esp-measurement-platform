#ifndef CONFIG_JSON_H
#define CONFIG_JSON_H

#include <ArduinoJson.h>

class DeviceMonitor;
class PluginRegistry;
class SensorHub;
class Storage;

// Builds the GET /api/v1/config document and checks POST bodies.
namespace ConfigJson
{
    // Device settings plus every available sensor type: whether it runs, the
    // sensor-bank poles it needs, its settings prefix, MQTT state topic,
    // parameters and alert limits (all read from its own settings scope).
    void writeConfig(JsonDocument& doc, const Storage& storage, const PluginRegistry& registry,
                     const DeviceMonitor* monitor);

    // nullptr when the body can be saved, otherwise why not (unknown sensor,
    // two sensors on one input).
    const char* problem(JsonObjectConst body, const PluginRegistry& registry);
}

#endif
