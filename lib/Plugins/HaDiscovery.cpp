#include "HaDiscovery.h"
#include "PlatformWiFi.h"
#include "Version.h"
#include "Board.h"

void HaDiscovery::addDeviceInfo(JsonObject& device, const String& deviceId, const char* name)
{
    device["identifiers"][0] = deviceId;
    if (name) device["name"] = name;
    device["manufacturer"] = "VB";
    device["model"] = Board::MODEL;
    device["sw_version"] = FW_VERSION;
    device["configuration_url"] = "http://" + WiFi.localIP().toString();
}

void HaDiscovery::addAvailability(JsonDocument& doc, const String& availabilityTopic)
{
    doc["availability_topic"] = availabilityTopic;
}
