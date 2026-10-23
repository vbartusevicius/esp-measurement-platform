#include "StatusJson.h"
#include <cmath>
#include <vector>
#include "ChipId.h"
#include "DeviceMonitor.h"
#include "IPlugin.h"
#include "Logger.h"
#include <WiFi.h>
#include "PluginConfig.h"
#include "TimeHelper.h"
#include "Version.h"

static float rounded(float v)
{
    return roundf(v * 100.0f) / 100.0f;
}

// NAN (no reading / limit off) becomes JSON null.
static void addNumber(JsonObject obj, const char* key, float value)
{
    if (std::isnan(value)) obj[key] = nullptr;
    else obj[key] = value;
}

static void writeSystem(JsonDocument& doc, const StatusJson::Sources& sources)
{
    doc["chip_id"] = ChipId::get();
    doc["active_plugin"] = sources.plugin ? sources.plugin->getId() : "";
    doc["active_plugin_name"] = sources.plugin ? sources.plugin->getName() : "None";
    doc["configured"] = PluginConfig::isComplete(*sources.storage, sources.plugin);
    doc["wifi_network"] = WiFi.SSID();
    doc["wifi_signal"] = String(WiFi.RSSI());
    doc["ip_address"] = WiFi.localIP().toString();
    doc["free_heap"] = ESP.getFreeHeap();
    doc["mqtt_connected"] = sources.mqttConnected;
    doc["firmware_version"] = FW_VERSION;
    doc["errors"] = sources.logger->errors();
    doc["warnings"] = sources.logger->warnings();

    char uptime[32];
    TimeHelper::getUptime(uptime);
    doc["uptime"] = uptime;
    doc["uptime_s"] = millis() / 1000UL;
}

static void writeStats(JsonDocument& doc, const IPlugin& plugin)
{
    std::vector<StatEntry> entries;
    plugin.getStats(entries);
    JsonArray stats = doc["stats"].to<JsonArray>();
    for (const StatEntry& e : entries) {
        JsonObject obj = stats.add<JsonObject>();
        obj["key"] = e.key;
        obj["label"] = e.label;
        obj["value"] = e.value;
        obj["numeric"] = e.numericValue;
    }
}

static void writeScreen(JsonDocument& doc, const IPlugin& plugin)
{
    ScreenModel screen;
    if (!plugin.getScreen(screen)) return;
    JsonObject s = doc["screen"].to<JsonObject>();
    s["kind"] = screen.kind;
    s["title"] = screen.title;
    addNumber(s, "value", screen.value);
    s["text"] = screen.format(screen.value);
    s["unit"] = screen.unit;
    s["decimals"] = screen.decimals;
    s["valid"] = screen.valid;
    addNumber(s, "scale_min", screen.scaleMin);
    addNumber(s, "scale_max", screen.scaleMax);
    s["trend_bucket_s"] = screen.trendBucketSec;
    JsonArray trend = s["trend"].to<JsonArray>();
    for (float v : screen.trend) trend.add(rounded(v));
    JsonArray lines = s["lines"].to<JsonArray>();
    for (const ScreenLine& line : screen.lines) {
        JsonObject l = lines.add<JsonObject>();
        l["label"] = line.label;
        l["value"] = line.value;
    }
    s["sensor_label"] = screen.sensorLabel;
    s["sensor_ok"] = screen.sensorOk;
    s["raw"] = screen.raw;
    s["signal"] = screen.signal;
    addNumber(s, "low_24h", screen.low24);
    addNumber(s, "high_24h", screen.high24);
}

static void writeDevice(JsonDocument& doc, const DeviceMonitor& monitor)
{
    const LimitMonitor& limits = monitor.limits();
    JsonObject lim = doc["limits"].to<JsonObject>();
    addNumber(lim, "low", limits.low());
    addNumber(lim, "high", limits.high());
    lim["state"] = LimitMonitor::stateName(limits.state());
    lim["alert"] = limits.alertPending();
    lim["trips"] = limits.trips();

    JsonObject relay = doc["relay"].to<JsonObject>();
    relay["available"] = monitor.relayAvailable();
    relay["on"] = monitor.relayOn();
    relay["activations"] = monitor.relayActivations();
    relay["mode"] = LimitMonitor::modeName(limits.relayMode());

    const EventLog& events = monitor.events();
    JsonArray arr = doc["events"].to<JsonArray>();
    for (size_t i = 0; i < events.size(); i++) {
        const EventLog::Entry& e = events.newest(i);
        JsonObject obj = arr.add<JsonObject>();
        obj["t"] = e.uptimeSec;
        obj["title"] = e.title;
        obj["detail"] = e.detail;
    }
}

void StatusJson::write(JsonDocument& doc, const Sources& sources)
{
    writeSystem(doc, sources);
    if (sources.plugin) {
        writeStats(doc, *sources.plugin);
        writeScreen(doc, *sources.plugin);
    }
    if (sources.monitor) writeDevice(doc, *sources.monitor);
}

void StatusJson::writeChart(JsonDocument& doc, const IPlugin* plugin)
{
    std::vector<float> points;
    int spanSeconds = 0;
    if (!plugin || !plugin->getChartData(points, spanSeconds) || points.empty()) return;
    JsonArray arr = doc["points"].to<JsonArray>();
    for (float v : points) arr.add(rounded(v));
    doc["span_seconds"] = spanSeconds;
    ScreenModel screen;
    doc["unit"] = plugin->getScreen(screen) ? screen.unit : "";
}
