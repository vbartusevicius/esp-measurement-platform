#ifndef HA_DISCOVERY_H
#define HA_DISCOVERY_H

#include <ArduinoJson.h>

class HaDiscovery
{
    public:
        static void addDeviceInfo(JsonObject& device, const String& deviceId, const char* name);
        static void addAvailability(JsonDocument& doc, const String& availabilityTopic);
};

#endif
