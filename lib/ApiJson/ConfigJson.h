#ifndef CONFIG_JSON_H
#define CONFIG_JSON_H

#include <ArduinoJson.h>

class DeviceMonitor;
class IPlugin;
class PluginRegistry;
class Storage;

// Builds GET /api/v1/plugins and GET /api/v1/config documents.
namespace ConfigJson
{
    void writePlugins(JsonDocument& doc, const PluginRegistry& registry, const IPlugin* active);

    // `inspected` is the plugin whose parameters are listed (the active one,
    // or the one picked in the sensor dropdown before saving).
    void writeConfig(JsonDocument& doc, const Storage& storage, const IPlugin* active,
                     const IPlugin* inspected, const DeviceMonitor* monitor);
}

#endif
