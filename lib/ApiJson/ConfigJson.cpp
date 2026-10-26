#include "ConfigJson.h"
#include <cstring>
#include <vector>
#include "Board.h"
#include "ChipId.h"
#include "DeviceMonitor.h"
#include "IPlugin.h"
#include "Parameter.h"
#include "PluginRegistry.h"
#include "ScopedSettings.h"
#include "SensorHub.h"
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

static void writeParameters(JsonObject sensor, const Settings& settings, const IPlugin& plugin)
{
    std::vector<ParameterDef> defs;
    std::vector<ParameterChoice> choices;
    plugin.getParameterDefs(defs);
    plugin.getParameterChoices(choices);

    JsonArray params = sensor["params"].to<JsonArray>();
    for (const ParameterDef& def : defs) {
        JsonObject obj = params.add<JsonObject>();
        obj["key"] = def.key;
        obj["label"] = def.label;
        obj["default"] = def.defaultValue;
        obj["type"] = typeName(def.type);
        obj["required"] = def.required;
        obj["value"] = settings.getParameter(def.key, def.defaultValue);

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

static void writeInputs(JsonObject sensor, uint8_t inputs)
{
    static const struct { uint8_t bit; int pole; const char* name; } POLES[] = {
        {Board::INPUT_MA, 3, "4-20mA"}, {Board::INPUT_V, 4, "0-10V"}, {Board::INPUT_IO1, 5, "IO1"},
        {Board::INPUT_IO2, 6, "IO2"}, {Board::INPUT_IO3, 7, "IO3"}, {Board::INPUT_IO4, 8, "IO4"},
    };
    JsonArray arr = sensor["inputs"].to<JsonArray>();
    for (const auto& p : POLES) {
        if (!(inputs & p.bit)) continue;
        JsonObject obj = arr.add<JsonObject>();
        obj["pole"] = p.pole;
        obj["name"] = p.name;
    }
}

void ConfigJson::writeConfig(JsonDocument& doc, const Storage& storage, const PluginRegistry& registry,
                             const DeviceMonitor* monitor)
{
    doc["chip_id"] = ChipId::get();
    doc["firmware_version"] = FW_VERSION;
    doc["device_name"] = storage.getParameter(Parameter::DEVICE_NAME, "");
    doc["mqtt_host"] = storage.getParameter(Parameter::MQTT_HOST, "");
    doc["mqtt_port"] = storage.getParameter(Parameter::MQTT_PORT, "1883");
    doc["mqtt_user"] = storage.getParameter(Parameter::MQTT_USER, "");
    // Never send the stored password to the browser, only whether one is set.
    doc["mqtt_pass_set"] = storage.getParameter(Parameter::MQTT_PASS, "").length() > 0;
    const String device = storage.getParameter(Parameter::MQTT_DEVICE, "");
    doc["mqtt_device"] = device;
    doc["relay_mode"] = storage.getParameter(Parameter::RELAY_MODE, "manual");
    doc["relay_source"] = storage.getParameter(Parameter::RELAY_SOURCE, "");
    doc["relay_available"] = monitor && monitor->relayAvailable();

    const std::vector<IPlugin*> enabled = SensorHub::enabled(storage, registry);
    JsonArray sensors = doc["sensors"].to<JsonArray>();
    // Enabled sensors first, in their order; then the rest of the registry
    std::vector<IPlugin*> order = enabled;
    for (IPlugin* p : registry.getAll()) {
        bool listed = false;
        for (IPlugin* e : enabled) listed |= e == p;
        if (!listed) order.push_back(p);
    }
    Storage& base = const_cast<Storage&>(storage);   // ScopedSettings is read-only here
    for (IPlugin* p : order) {
        const ScopedSettings settings(&base, ScopedSettings::prefixFor(p->getId()));
        bool on = false;
        for (IPlugin* e : enabled) on |= e == p;
        JsonObject s = sensors.add<JsonObject>();
        s["id"] = p->getId();
        s["name"] = p->getName();
        s["prefix"] = settings.prefix();
        s["enabled"] = on;
        s["topic"] = (device.isEmpty() ? String("esp_") + ChipId::get() : device) + "/stat/" + p->getId();
        writeInputs(s, p->inputs());
        writeParameters(s, settings, *p);
        JsonObject lim = s["limits"].to<JsonObject>();
        lim["low"] = settings.getParameter(Parameter::LIMIT_LOW, "");
        lim["high"] = settings.getParameter(Parameter::LIMIT_HIGH, "");
        lim["hysteresis"] = settings.getParameter(Parameter::LIMIT_HYSTERESIS, "");
        lim["low_on"] = DeviceMonitor::limitEnabled(settings, Parameter::LIMIT_LOW_ON, Parameter::LIMIT_LOW) ? "1" : "0";
        lim["high_on"] = DeviceMonitor::limitEnabled(settings, Parameter::LIMIT_HIGH_ON, Parameter::LIMIT_HIGH) ? "1" : "0";
    }
}

const char* ConfigJson::problem(JsonObjectConst body, const PluginRegistry& registry)
{
    if (!body[Parameter::SENSORS].is<const char*>()) return nullptr;
    const String list = body[Parameter::SENSORS].as<const char*>();
    const std::vector<IPlugin*> plugins = SensorHub::parse(list, registry);
    size_t ids = list.isEmpty() ? 0 : 1;
    for (unsigned int i = 0; i < list.length(); i++) ids += list.c_str()[i] == ',';
    if (plugins.size() != ids) return "Unknown or repeated sensor";
    if (SensorHub::clash(plugins)) return "Two sensors need the same input";
    return nullptr;
}
