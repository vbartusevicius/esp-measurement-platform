#include "DistancePluginBase.h"
#include <ArduinoJson.h>
#include "HaDiscovery.h"

void DistancePluginBase::setup(HAL* hal, Storage* storage, Logger* logger, LedController* led)
{
    this->hal = hal;
    this->storage = storage;
    this->logger = logger;
    this->measuredDistance = 0.0f;
    this->relativeDistance = 0.0f;
    this->absoluteDistance = 0.0f;
    this->sensorConnected = false;
    this->currentVolume = 0.0f;
    this->lastRawDistance = 0.0f;
    this->totalVolume = atof(this->storage->getParameter(PARAM_TOTAL_VOLUME, "0").c_str());
    this->distFilter.reset();
    this->flowCalc.reset();
    this->usageTracker.reset();
    this->levelTrend.reset();
    this->levelExtremes.reset();
    this->levelHistory.reset();
    this->lastSignal = "";

    this->avgSampleCount = atoi(this->storage->getParameter(PARAM_AVG_SAMPLE_COUNT, "10").c_str());
    this->deadbandM = atof(this->storage->getParameter(PARAM_DEADBAND_CM, "10").c_str()) / 100.0f;
    this->snapAfterSamples = atoi(this->storage->getParameter(PARAM_SNAP_SAMPLES, "5").c_str());
    if (this->snapAfterSamples < 1) this->snapAfterSamples = 1;
    this->maxRateMPerMin = atof(this->storage->getParameter(PARAM_MAX_RATE_CM_MIN, "0").c_str()) / 100.0f;
    this->emptyDistM = atof(this->storage->getParameter(PARAM_DISTANCE_EMPTY).c_str()) / 100.0f;
    this->fullDistM = atof(this->storage->getParameter(PARAM_DISTANCE_FULL).c_str()) / 100.0f;

    int interval = this->storage->getParameter(PARAM_SAMPLING_INTERVAL, "10").toInt();
    this->samplingIntervalSec = interval < 1 ? 1 : interval;

    this->loadPluginConfig();
    this->setupPins();
}

void DistancePluginBase::loop()
{
    float raw = this->readSensor();
    this->lastRawDistance = raw;

    this->distFilter.process(raw, this->avgSampleCount, this->deadbandM,
                             this->snapAfterSamples, this->maxRateMPerMin, millis());
    this->measuredDistance = this->distFilter.getFiltered();
    this->relativeDistance = this->computeRelative(this->measuredDistance, this->emptyDistM, this->fullDistM);
    this->absoluteDistance = this->computeAbsolute(this->measuredDistance, this->emptyDistM, this->fullDistM);

    if (this->sensorConnected) {
        float percent = this->relativeDistance * 100.0f;
        this->levelTrend.add(percent, millis());
        this->levelExtremes.update(percent, millis());
        this->levelHistory.add(percent, millis());
    }

    // Volume-derived metrics (uses raw float precision, no rounding)
    if (this->totalVolume > 0) {
        this->currentVolume = this->relativeDistance * this->totalVolume;
        this->flowCalc.update(this->currentVolume, millis());
        this->usageTracker.update(this->currentVolume, millis());
    }
}

// --- Parameters ---

void DistancePluginBase::getParameterDefs(std::vector<ParameterDef>& defs) const
{
    this->addPluginParameterDefs(defs);
    defs.push_back({PARAM_AVG_SAMPLE_COUNT, "Median Window Samples", "10", ParameterDef::NUMBER, false});
    defs.push_back({PARAM_SAMPLING_INTERVAL, "Sampling Interval (s)", "10", ParameterDef::NUMBER, false});
    defs.push_back({PARAM_DEADBAND_CM, "Change Deadband (cm)", "10", ParameterDef::NUMBER, false});
    defs.push_back({PARAM_SNAP_SAMPLES, "Step Confirm Samples", "5", ParameterDef::NUMBER, false});
    defs.push_back({PARAM_MAX_RATE_CM_MIN, "Max Change Rate (cm/min, 0=off)", "0", ParameterDef::NUMBER, false});
    defs.push_back({PARAM_TOTAL_VOLUME, "Total Volume (L)", "", ParameterDef::NUMBER, false});
}

// --- Stats ---

void DistancePluginBase::getStats(std::vector<StatEntry>& entries) const
{
    entries.push_back({"Level", String(this->relativeDistance * 100, 1) + "%", this->relativeDistance, StatEntry::PROGRESS, true, "level"});
    entries.push_back({"Depth", String(this->absoluteDistance, 2) + " m", this->absoluteDistance, StatEntry::TEXT, true, "depth"});
    if (this->totalVolume > 0) {
        entries.push_back({"Volume", String(this->currentVolume, 0) + " L", this->currentVolume, StatEntry::TEXT, true, "volume"});
        entries.push_back({"Capacity", String(this->totalVolume, 0) + " L", this->totalVolume, StatEntry::TEXT, false, "capacity"});
    }
    entries.push_back({"Distance", String(this->measuredDistance, 3) + " m", this->measuredDistance, StatEntry::TEXT, false, "distance"});
    entries.push_back({"Raw", String(this->lastRawDistance, 3) + " m", this->lastRawDistance, StatEntry::TEXT, false, "raw"});
    entries.push_back({"Sensor", this->sensorConnected ? "Connected" : "Disconnected", this->sensorConnected ? 1.0f : 0.0f, StatEntry::TEXT, false, "sensor"});
    if (this->totalVolume > 0) {
        float rate = this->flowCalc.getRate();
        String rateStr = (rate >= 0 ? "+" : "") + String(rate, 2) + " L/min";
        entries.push_back({"Flow Rate", rateStr, rate, StatEntry::TEXT, true, "flow_rate"});

        float usage = this->usageTracker.getUsageLiters();
        entries.push_back({"Usage 24h", String(usage, 1) + " L", usage, StatEntry::TEXT, false, "usage_24h"});
    }
}

// --- Screen model (OLED + WebUI) ---

bool DistancePluginBase::getScreen(ScreenModel& model) const
{
    model.kind = "level";
    model.title = "TANK";
    model.value = this->relativeDistance * 100.0f;
    model.unit = "%";
    model.decimals = 0;
    model.valid = this->sensorConnected;
    model.scaleMin = 0.0f;
    model.scaleMax = 100.0f;
    model.trend = this->levelTrend.values();
    model.trendBucketSec = this->levelTrend.getBucketMs() / 1000UL;
    model.sensorLabel = "SENS";
    model.sensorOk = this->sensorConnected;
    model.raw = String(this->lastRawDistance * 100.0f, 1) + "cm";
    model.signal = this->lastSignal;
    if (this->levelExtremes.valid()) {
        model.low24 = this->levelExtremes.min();
        model.high24 = this->levelExtremes.max();
    }
    if (this->totalVolume > 0) {
        float rate = this->flowCalc.getRate();
        model.lines.push_back({"VOL", String(this->currentVolume, 0) + "L"});
        model.lines.push_back({"FLW", (rate >= 0 ? "+" : "") + String(rate, 1) + "Lm"});   // 10 chars/row on the OLED
    } else {
        model.lines.push_back({"DEP", String(this->absoluteDistance, 2) + "m"});
        model.lines.push_back({"DST", String(this->measuredDistance, 2) + "m"});
    }
    return true;
}

bool DistancePluginBase::getChartData(std::vector<float>& points, int& spanSeconds) const
{
    points = this->levelHistory.values();
    spanSeconds = (int)(this->levelHistory.getBucketMs() / 1000UL);
    return true;
}

// --- MQTT ---

void DistancePluginBase::publishMqtt(MQTTClient& client, const String& baseTopic)
{
    JsonDocument doc;
    String json;

    doc["relative"] = this->relativeDistance;
    doc["absolute"] = this->absoluteDistance;
    doc["measured"] = this->measuredDistance;
    doc["raw"] = this->lastRawDistance;
    doc["connected"] = this->sensorConnected;
    if (this->totalVolume > 0) {
        doc["volume"] = this->currentVolume;
        doc["flow_rate"] = this->flowCalc.getRate();
        doc["usage_24h"] = this->usageTracker.getUsageLiters();
    }
    serializeJson(doc, json);

    client.publish(baseTopic.c_str(), json.c_str(), false, 0);
}

void DistancePluginBase::publishCommonHaSensors(MQTTClient& client, const HaDiscoveryContext& ctx)
{
    const String& deviceId = ctx.deviceId;
    const String& stateTopic = ctx.stateTopic;

    if (this->totalVolume > 0) {
        // Volume sensor (L)
        {
            JsonDocument doc;
            doc["state_topic"] = stateTopic;
            doc["value_template"] = "{{ value_json.volume | round(0) }}";
            doc["unit_of_measurement"] = "L";
            doc["device_class"] = "volume";
            doc["name"] = "Volume";
            doc["unique_id"] = deviceId + "_volume";
            doc["icon"] = "mdi:cube-outline";
            doc["state_class"] = "measurement";

            JsonObject device = doc["device"].to<JsonObject>();
            HaDiscovery::addDeviceInfo(device, deviceId, ctx.nameOr(this->getDeviceName()));
            HaDiscovery::addAvailability(doc, ctx.availabilityTopic);

            String json;
            serializeJson(doc, json);
            client.publish(("homeassistant/sensor/" + deviceId + "/volume/config").c_str(), json.c_str(), true, 1);
        }

        // Usage over the last 24 h (L)
        {
            JsonDocument doc;
            doc["state_topic"] = stateTopic;
            doc["value_template"] = "{{ value_json.usage_24h | round(1) }}";
            doc["unit_of_measurement"] = "L";
            doc["device_class"] = "volume";
            doc["name"] = "Usage 24h";
            doc["unique_id"] = deviceId + "_usage_24h";
            doc["icon"] = "mdi:chart-bar";
            doc["state_class"] = "measurement";

            JsonObject device = doc["device"].to<JsonObject>();
            HaDiscovery::addDeviceInfo(device, deviceId, ctx.nameOr(this->getDeviceName()));
            HaDiscovery::addAvailability(doc, ctx.availabilityTopic);

            String json;
            serializeJson(doc, json);
            client.publish(("homeassistant/sensor/" + deviceId + "/usage_24h/config").c_str(), json.c_str(), true, 1);
        }

        // Flow rate sensor (L/min)
        {
            JsonDocument doc;
            doc["state_topic"] = stateTopic;
            doc["value_template"] = "{{ value_json.flow_rate | round(2) }}";
            doc["unit_of_measurement"] = "L/min";
            doc["device_class"] = "volume_flow_rate";
            doc["name"] = "Flow Rate";
            doc["unique_id"] = deviceId + "_flow_rate";
            doc["icon"] = "mdi:swap-vertical";
            doc["state_class"] = "measurement";

            JsonObject device = doc["device"].to<JsonObject>();
            HaDiscovery::addDeviceInfo(device, deviceId, ctx.nameOr(this->getDeviceName()));
            HaDiscovery::addAvailability(doc, ctx.availabilityTopic);

            String json;
            serializeJson(doc, json);
            client.publish(("homeassistant/sensor/" + deviceId + "/flow_rate/config").c_str(), json.c_str(), true, 1);
        }
    }

    // Sensor connectivity (binary sensor, diagnostics)
    {
        JsonDocument doc;
        doc["state_topic"] = stateTopic;
        doc["value_template"] = "{{ 'ON' if value_json.connected else 'OFF' }}";
        doc["device_class"] = "connectivity";
        doc["name"] = "Sensor";
        doc["unique_id"] = deviceId + "_sensor_connected";
        doc["entity_category"] = "diagnostic";

        JsonObject device = doc["device"].to<JsonObject>();
        HaDiscovery::addDeviceInfo(device, deviceId, ctx.nameOr(this->getDeviceName()));
        HaDiscovery::addAvailability(doc, ctx.availabilityTopic);

        String json;
        serializeJson(doc, json);
        client.publish(("homeassistant/binary_sensor/" + deviceId + "/connected/config").c_str(), json.c_str(), true, 1);
    }
}

// --- Display ---

int DistancePluginBase::getDisplayPageCount() const { return 1; }

int DistancePluginBase::getSamplingInterval() const
{
    return this->samplingIntervalSec;
}

int DistancePluginBase::renderDisplayPage(U8G2& u8g2, int page, int width, int height) const
{
    // Progress bar
    const int barHeight = 16;
    const char* label = "N/A";
    int boxWidth = 0;
    char percentStr[8];

    if (this->sensorConnected) {
        boxWidth = (width - 2) * this->relativeDistance;
        snprintf(percentStr, sizeof(percentStr), "%.0f%%", this->relativeDistance * 100);
        label = percentStr;
    }

    u8g2.drawFrame(0, 0, width, barHeight);
    u8g2.drawBox(1, 1, boxWidth, barHeight - 2);

    u8g2.setFontMode(1);
    u8g2.setDrawColor(2);
    u8g2.setFont(u8g2_font_5x7_tr);
    int strW = u8g2.getStrWidth(label);
    u8g2.drawStr((width - strW) / 2, u8g2.getAscent() + (barHeight - u8g2.getAscent()) / 2 - 1, label);

    // Sensor status
    int cursorY = barHeight;
    u8g2.setDrawColor(1);
    u8g2.setFontMode(0);
    const char* sensorGlyph = this->sensorConnected ? "[+]" : "[ ]";
    u8g2.setFont(u8g2_font_5x7_tr);
    u8g2.drawStr(0, cursorY + 8, "Sensor:");
    int gw = u8g2.getStrWidth(sensorGlyph);
    u8g2.drawStr((width / 2) - gw, cursorY + 8, sensorGlyph);
    cursorY += 8;

    return cursorY;
}
