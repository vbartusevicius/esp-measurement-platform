#include "HaDiscovery.h"
#include "Board.h"
#include "PlatformWiFi.h"
#include "Version.h"

void HaDiscovery::publish(MQTTClient& client, const HaDiscoveryContext& ctx, const HaEntity& entity,
                          const char* deviceName, void (*extra)(JsonDocument&, const HaDiscoveryContext&))
{
    JsonDocument doc;
    doc["name"] = entity.name;
    doc["unique_id"] = ctx.deviceId + "_" + entity.uniqueSuffix;
    doc["state_topic"] = ctx.stateTopic;
    if (entity.valueTemplate) doc["value_template"] = entity.valueTemplate;
    if (entity.unit) doc["unit_of_measurement"] = entity.unit;
    if (entity.deviceClass) doc["device_class"] = entity.deviceClass;
    if (entity.icon) doc["icon"] = entity.icon;
    if (entity.measurement) doc["state_class"] = "measurement";
    if (entity.diagnostic) doc["entity_category"] = "diagnostic";
    doc["availability_topic"] = ctx.availabilityTopic;

    JsonObject device = doc["device"].to<JsonObject>();
    device["identifiers"][0] = ctx.deviceId;
    if (deviceName) device["name"] = deviceName;
    device["manufacturer"] = "VB";
    device["model"] = Board::MODEL;
    device["sw_version"] = FW_VERSION;
    device["configuration_url"] = "http://" + WiFi.localIP().toString();

    if (extra) extra(doc, ctx);

    String topic = String("homeassistant/") + entity.component + "/" + ctx.deviceId + "/";
    if (entity.objectId[0]) topic += String(entity.objectId) + "/";
    topic += "config";

    String json;
    serializeJson(doc, json);
    client.publish(topic.c_str(), json.c_str(), true, 1);
}

void HaDiscovery::publishJson(MQTTClient& client, const String& topic, JsonDocument& doc)
{
    String json;
    serializeJson(doc, json);
    client.publish(topic.c_str(), json.c_str(), false, 0);
}
