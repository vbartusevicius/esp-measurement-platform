#ifndef HA_DISCOVERY_H
#define HA_DISCOVERY_H

#include <ArduinoJson.h>

// Shared helpers for Home Assistant MQTT discovery configs.
class HaDiscovery
{
    public:
        // Fills the "device" object with identity + metadata (sw_version,
        // configuration_url). One HA device per physical board (deviceId).
        // Pass name == nullptr to merge metadata into the device without renaming it
        // (e.g. system diagnostics sharing the device with plugin sensors).
        static void addDeviceInfo(JsonObject& device, const String& deviceId, const char* name);

        // Links an entity to the device availability LWT (esp/<id>/availability).
        static void addAvailability(JsonDocument& doc, const String& deviceId);
};

#endif
