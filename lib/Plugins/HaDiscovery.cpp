#include "HaDiscovery.h"
#include <ESP8266WiFi.h>
#include "Version.h"

void HaDiscovery::addDeviceInfo(JsonObject& device, const String& deviceId, const char* name)
{
    device["identifiers"][0] = deviceId;
    if (name) device["name"] = name;
    device["manufacturer"] = "VB";
    device["model"] = "ESP8266";
    device["sw_version"] = FW_VERSION;
    device["configuration_url"] = "http://" + WiFi.localIP().toString();
}

void HaDiscovery::addAvailability(JsonDocument& doc, const String& availabilityTopic)
{
    doc["availability_topic"] = availabilityTopic;
}
