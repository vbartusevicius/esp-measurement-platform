#include "DistancePluginBase.h"
#include "HAL.h"
#include "Storage.h"

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

    const unsigned long now = this->hal->millis();
    this->distFilter.process(raw, this->avgSampleCount, this->deadbandM,
                             this->snapAfterSamples, this->maxRateMPerMin, now);
    this->measuredDistance = this->distFilter.getFiltered();
    this->relativeDistance = this->computeRelative(this->measuredDistance, this->emptyDistM, this->fullDistM);
    this->absoluteDistance = this->computeAbsolute(this->measuredDistance, this->emptyDistM, this->fullDistM);

    if (this->sensorConnected) {
        float percent = this->relativeDistance * 100.0f;
        this->levelTrend.add(percent, now);
        this->levelExtremes.update(percent, now);
        this->levelHistory.add(percent, now);
    }

    // Volume-derived metrics (uses raw float precision, no rounding)
    if (this->totalVolume > 0) {
        this->currentVolume = this->relativeDistance * this->totalVolume;
        this->flowCalc.update(this->currentVolume, now);
        this->usageTracker.update(this->currentVolume, now);
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
    entries.push_back({"level", "Level", String(this->relativeDistance * 100, 1) + "%", this->relativeDistance});
    entries.push_back({"depth", "Depth", String(this->absoluteDistance, 2) + " m", this->absoluteDistance});
    if (this->totalVolume > 0) {
        entries.push_back({"volume", "Volume", String(this->currentVolume, 0) + " L", this->currentVolume});
        entries.push_back({"capacity", "Capacity", String(this->totalVolume, 0) + " L", this->totalVolume});
    }
    entries.push_back({"distance", "Distance", String(this->measuredDistance, 3) + " m", this->measuredDistance});
    entries.push_back({"raw", "Raw", String(this->lastRawDistance, 3) + " m", this->lastRawDistance});
    entries.push_back({"sensor", "Sensor", this->sensorConnected ? "Connected" : "Disconnected", this->sensorConnected ? 1.0f : 0.0f});
    if (this->totalVolume > 0) {
        float rate = this->flowCalc.getRate();
        entries.push_back({"flow_rate", "Flow Rate", (rate >= 0 ? "+" : "") + String(rate, 2) + " L/min", rate});
        float usage = this->usageTracker.getUsageLiters();
        entries.push_back({"usage_24h", "Usage 24h", String(usage, 1) + " L", usage});
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
    HaDiscovery::publishJson(client, baseTopic, doc);
}

void DistancePluginBase::publishCommonHaSensors(MQTTClient& client, const HaDiscoveryContext& ctx)
{
    static const HaEntity volumeEntities[] = {
        {"sensor", "volume", "volume", "Volume", "{{ value_json.volume | round(0) }}", "L", "volume", "mdi:cube-outline", true, false},
        {"sensor", "usage_24h", "usage_24h", "Usage 24h", "{{ value_json.usage_24h | round(1) }}", "L", "volume", "mdi:chart-bar", true, false},
        {"sensor", "flow_rate", "flow_rate", "Flow Rate", "{{ value_json.flow_rate | round(2) }}", "L/min", "volume_flow_rate", "mdi:swap-vertical", true, false},
    };
    static const HaEntity connected =
        {"binary_sensor", "connected", "sensor_connected", "Sensor", "{{ 'ON' if value_json.connected else 'OFF' }}", nullptr, "connectivity", nullptr, false, true};

    const char* deviceName = ctx.nameOr(this->getDeviceName());
    if (this->totalVolume > 0) {
        for (const HaEntity& entity : volumeEntities) HaDiscovery::publish(client, ctx, entity, deviceName);
    }
    HaDiscovery::publish(client, ctx, connected, deviceName);
}

int DistancePluginBase::getSamplingInterval() const
{
    return this->samplingIntervalSec;
}
