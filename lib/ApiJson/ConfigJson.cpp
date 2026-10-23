#include "ConfigJson.h"
#include <cstring>
#include <vector>
#include "ChipId.h"
#include "DeviceMonitor.h"
#include "IPlugin.h"
#include "Parameter.h"
#include "PluginRegistry.h"
#include "Storage.h"
#include "Version.h"

static const char* typeName(ParameterDef::Type type)
{
    switch (type) {
        case ParameterDef::NUMBER: return "number";
        case ParameterDef::PASSWORD: return "password";
        case ParameterDef::SELECT: return "select";
        default: return "text";
    }
}

static void writeParameters(JsonDocument& doc, const Storage& storage, const IPlugin& plugin)
{
    std::vector<ParameterDef> defs;
    std::vector<ParameterChoice> choices;
    plugin.getParameterDefs(defs);
    plugin.getParameterChoices(choices);

    JsonArray params = doc["plugin_params"].to<JsonArray>();
    for (const ParameterDef& def : defs) {
        JsonObject obj = params.add<JsonObject>();
        obj["key"] = def.key;
        obj["label"] = def.label;
        obj["default"] = def.defaultValue;
        obj["type"] = typeName(def.type);
        obj["required"] = def.required;
        obj["value"] = storage.getParameter(def.key, def.defaultValue);

        for (const ParameterChoice& choice : choices) {
            if (strcmp(choice.param, def.key) != 0) continue;
            JsonObject option = obj["options"].add<JsonObject>();
            option["value"] = choice.value;
            option["label"] = choice.label;
            if (choice.fills.empty()) continue;
            JsonObject preset = obj["presets"][choice.value].to<JsonObject>();
            for (const ParameterFill& fill : choice.fills) preset[fill.key] = fill.value;
        }
    }
}

void ConfigJson::writePlugins(JsonDocument& doc, const PluginRegistry& registry, const IPlugin* active)
{
    JsonArray arr = doc["plugins"].to<JsonArray>();
    for (const IPlugin* p : registry.getAll()) {
        JsonObject obj = arr.add<JsonObject>();
        obj["id"] = p->getId();
        obj["name"] = p->getName();
        obj["active"] = (p == active);
    }
}

void ConfigJson::writeConfig(JsonDocument& doc, const Storage& storage, const IPlugin* active,
                             const IPlugin* inspected, const DeviceMonitor* monitor)
{
    doc["active_plugin"] = active ? active->getId() : "";
    doc["chip_id"] = ChipId::get();
    doc["firmware_version"] = FW_VERSION;
    doc["device_name"] = storage.getParameter(Parameter::DEVICE_NAME, "");
    doc["mqtt_host"] = storage.getParameter(Parameter::MQTT_HOST, "");
    doc["mqtt_port"] = storage.getParameter(Parameter::MQTT_PORT, "1883");
    doc["mqtt_user"] = storage.getParameter(Parameter::MQTT_USER, "");
    doc["mqtt_pass"] = storage.getParameter(Parameter::MQTT_PASS, "");
    doc["mqtt_device"] = storage.getParameter(Parameter::MQTT_DEVICE, "");
    doc["mqtt_topic"] = storage.getParameter(Parameter::MQTT_TOPIC, "");

    doc["limit_low"] = storage.getParameter(Parameter::LIMIT_LOW, "");
    doc["limit_high"] = storage.getParameter(Parameter::LIMIT_HIGH, "");
    doc["limit_hysteresis"] = storage.getParameter(Parameter::LIMIT_HYSTERESIS, "");
    doc["relay_mode"] = storage.getParameter(Parameter::RELAY_MODE, "manual");
    if (monitor) {
        doc["limit_low_on"] = monitor->limitEnabled(Parameter::LIMIT_LOW_ON, Parameter::LIMIT_LOW) ? "1" : "0";
        doc["limit_high_on"] = monitor->limitEnabled(Parameter::LIMIT_HIGH_ON, Parameter::LIMIT_HIGH) ? "1" : "0";
    }
    doc["relay_available"] = monitor && monitor->relayAvailable();

    if (inspected) writeParameters(doc, storage, *inspected);
    else doc["plugin_params"].to<JsonArray>();
}
