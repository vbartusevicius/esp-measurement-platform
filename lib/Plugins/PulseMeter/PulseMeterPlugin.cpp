#include "PulseMeterPlugin.h"
#include <cstdlib>
#include "HAL.h"
#include "LedController.h"
#include "Logger.h"
#include "Settings.h"

PulseMeterPlugin* PulseMeterPlugin::instance = nullptr;

// millis() is IRAM-safe on the ESP32, so pulses during a flash write still count.
IRAM_ATTR void PulseMeterPlugin::pulseISR()
{
    if (instance) instance->onPulse(millis());
}

const PulseMeterPlugin::Medium PulseMeterPlugin::MEDIA[] = {
    {"water", "Water", "Water", "WATR", "water", "mdi:water", "moisture"},
    {"gas", "Gas", "Gas", "GAS", "gas", "mdi:fire", "problem"},
    {"oil", "Oil / fuel", "Oil", "OIL", "volume", "mdi:oil", "problem"},
    {"other", "Other (volume)", "Meter", "MTR", "volume", "mdi:counter", "problem"},
};

const char* PulseMeterPlugin::getId() const { return "pulse_meter"; }
const char* PulseMeterPlugin::getName() const { return "Pulse Meter (water, gas, oil)"; }

void PulseMeterPlugin::setup(HAL* hal, Settings* storage, Logger* logger, LedController* led)
{
    this->hal = hal;
    this->storage = storage;
    this->logger = logger;
    this->led = led;

    const String medium = this->storage->getParameter(PARAM_MEDIUM, "water");
    this->medium = &MEDIA[0];
    for (const Medium& m : MEDIA) {
        if (medium == m.id) this->medium = &m;
    }
    this->litersPerPulse = this->storage->getParameter(PARAM_LITERS_PER_PULSE, "1").toFloat();
    if (this->litersPerPulse <= 0.0f) this->litersPerPulse = 1.0f;
    this->minPulseGapMs = (unsigned long)this->storage->getParameter(PARAM_MIN_PULSE_GAP_MS, "50").toInt();
    this->leakHours = this->storage->getParameter(PARAM_LEAK_HOURS, "24").toInt();

    this->total = atof(this->storage->getParameter(KEY_TOTAL_LITERS, "0").c_str());
    this->applyMeterReading();
    this->persistedTotal = this->total;
    this->lastPersistMs = this->hal->millis();
    this->pendingPulses = 0;
    this->anyPulse = false;
    this->pulseCount = 0;
    this->flow = 0.0f;
    for (int i = 0; i < USAGE_HOURS; i++) this->hourSlot[i] = -1;
    for (int i = 0; i < HISTORY_BARS; i++) this->barSlot[i] = -1;
    this->flowTrend.reset();
    this->flowExtremes.reset();

    this->hal->pinMode(PULSE_PIN, INPUT_PULLUP);
    instance = this;
    this->hal->attachInterrupt(this->hal->pinToInterrupt(PULSE_PIN), pulseISR, FALLING);
    this->logger->info(String(this->medium->noun) + " meter: " + String(this->litersPerPulse, 1) + " L/pulse, register " +
                       String(this->total / 1000.0, 3) + " m3");
}

// A new "meter reading" setting (the dial, in m3) replaces the counted total once.
void PulseMeterPlugin::applyMeterReading()
{
    const String reading = this->storage->getParameter(PARAM_METER_READING, "");
    if (reading.isEmpty() || reading == this->storage->getParameter(KEY_READING_APPLIED, "")) return;
    this->total = atof(reading.c_str()) * 1000.0;
    this->storage->saveParameter(KEY_TOTAL_LITERS, String(this->total, 1));
    this->storage->saveParameter(KEY_READING_APPLIED, reading);
}

IRAM_ATTR void PulseMeterPlugin::onPulse(unsigned long nowMs)
{
    if (this->anyPulse && nowMs - this->lastEdgeMs < this->minPulseGapMs) return;
    this->lastEdgeMs = nowMs;
    this->previousPulseMs = this->lastPulseMs;
    this->lastPulseMs = nowMs;
    this->anyPulse = true;
    this->pendingPulses = this->pendingPulses + 1;
}

void PulseMeterPlugin::loop()
{
    noInterrupts();
    const unsigned long pulses = this->pendingPulses;
    this->pendingPulses = 0;
    interrupts();

    const unsigned long now = this->hal->millis();
    if (pulses > 0) {
        this->pulseCount += pulses;
        this->addLiters(pulses * (double)this->litersPerPulse, now);
        if (this->led) this->led->click();
    } else {
        this->addLiters(0.0, now);   // rolls the hour / bar buckets on
    }
    this->flow = this->computeFlow(now);
    this->flowTrend.add(this->flow, now);
    this->flowExtremes.update(this->flow, now);

    if (this->total != this->persistedTotal && now - this->lastPersistMs >= PERSIST_INTERVAL_MS) this->persist();
}

void PulseMeterPlugin::persist()
{
    this->storage->saveParameter(KEY_TOTAL_LITERS, String(this->total, 1));
    this->persistedTotal = this->total;
    this->lastPersistMs = this->hal->millis();
}

void PulseMeterPlugin::addLiters(double liters, unsigned long nowMs)
{
    this->total += liters;
    const long hour = (long)(nowMs / 3600000UL);
    const int h = (int)(hour % USAGE_HOURS);
    if (this->hourSlot[h] != hour) {
        this->hourSlot[h] = hour;
        this->hourLiters[h] = 0.0f;
    }
    this->hourLiters[h] += (float)liters;

    const long bar = (long)(nowMs / HISTORY_BAR_MS);
    const int b = (int)(bar % HISTORY_BARS);
    if (this->barSlot[b] != bar) {
        this->barSlot[b] = bar;
        this->barLiters[b] = 0.0f;
    }
    this->barLiters[b] += (float)liters;
}

// L/min from the last pulse interval; while no further pulse arrives the
// rate can be at most one pulse per elapsed time, so it decays towards 0.
float PulseMeterPlugin::computeFlow(unsigned long nowMs) const
{
    if (!this->anyPulse || this->previousPulseMs == 0 || nowMs - this->lastPulseMs >= FLOW_TIMEOUT_MS) return 0.0f;
    const unsigned long interval = this->lastPulseMs - this->previousPulseMs;
    const unsigned long elapsed = nowMs - this->lastPulseMs;
    const unsigned long basis = elapsed > interval ? elapsed : interval;
    if (basis == 0) return 0.0f;
    return this->litersPerPulse * 60000.0f / (float)basis;
}

float PulseMeterPlugin::usage24hLiters() const
{
    const long hour = (long)(this->hal->millis() / 3600000UL);
    float sum = 0.0f;
    for (int i = 0; i < USAGE_HOURS; i++) {
        if (this->hourSlot[i] >= 0 && hour - this->hourSlot[i] < USAGE_HOURS) sum += this->hourLiters[i];
    }
    return sum;
}

// Hours in a row, up to and including the current one, with some flow: flow
// that never stops for a whole hour points at a leak (dripping tap, cistern).
int PulseMeterPlugin::continuousFlowHours() const
{
    const long hour = (long)(this->hal->millis() / 3600000UL);
    int run = 0;
    for (int back = 0; back < USAGE_HOURS; back++) {
        const long slot = hour - back;
        if (slot < 0) break;
        const int i = (int)(slot % USAGE_HOURS);
        if (this->hourSlot[i] != slot || this->hourLiters[i] <= 0.0f) break;
        run++;
    }
    return run;
}

bool PulseMeterPlugin::leak() const
{
    return this->leakHours > 0 && this->continuousFlowHours() >= this->leakHours;
}

// --- Parameters ---

void PulseMeterPlugin::getParameterDefs(std::vector<ParameterDef>& defs) const
{
    defs.push_back({PARAM_MEDIUM, "Medium", "water", ParameterDef::SELECT, false});
    defs.push_back({PARAM_LITERS_PER_PULSE, "Litres per Pulse (K)", "1", ParameterDef::NUMBER, true});
    defs.push_back({PARAM_METER_READING, "Meter Reading (m3)", "", ParameterDef::NUMBER, false});
    defs.push_back({PARAM_MIN_PULSE_GAP_MS, "Min Pulse Gap (ms)", "50", ParameterDef::NUMBER, false});
    defs.push_back({PARAM_LEAK_HOURS, "Leak Alert after (h, 0=off)", "24", ParameterDef::NUMBER, false});
}

void PulseMeterPlugin::getParameterChoices(std::vector<ParameterChoice>& choices) const
{
    for (const Medium& m : MEDIA) choices.push_back({PARAM_MEDIUM, m.id, m.label, {}});
}

// --- Stats ---

void PulseMeterPlugin::getStats(std::vector<StatEntry>& entries) const
{
    const float usage = this->usage24hLiters();
    entries.push_back({"medium", "Medium", this->medium->id, 0.0f});
    entries.push_back({"total_m3", "Meter Reading", String(this->total / 1000.0, 3) + " m\xC2\xB3", (float)(this->total / 1000.0)});
    entries.push_back({"flow_rate", "Flow Rate", String(this->flow, 1) + " L/min", this->flow});
    entries.push_back({"usage_24h", "Usage 24h", String(usage, 0) + " L", usage});
    entries.push_back({"continuous_h", "Continuous Flow", String(this->continuousFlowHours()) + " h", (float)this->continuousFlowHours()});
    entries.push_back({"pulses", "Pulses since Start", String(this->pulseCount), (float)this->pulseCount});
    entries.push_back({"liters_per_pulse", "Litres per Pulse", String(this->litersPerPulse, 1) + " L", this->litersPerPulse});
    if (this->leak()) entries.push_back({"leak", "Leak", "CONTINUOUS FLOW", 1.0f});
}

// --- Screen model (OLED + WebUI) ---

// "12s", "4m", "3h", "2d": fits the 64 px OLED row
static String ageText(unsigned long ms)
{
    const unsigned long s = ms / 1000UL;
    if (s < 60UL) return String(s) + "s";
    if (s < 3600UL) return String(s / 60UL) + "m";
    if (s < 86400UL) return String(s / 3600UL) + "h";
    return String(s / 86400UL) + "d";
}

bool PulseMeterPlugin::getScreen(ScreenModel& model) const
{
    model.kind = "meter";
    model.title = this->medium->title;
    model.value = this->flow;        // what the MIN/MAX limits compare, e.g. a high-flow alarm closes a valve
    model.unit = "L/min";
    model.decimals = 1;
    model.valid = true;
    model.scaleMin = 0.0f;
    model.trend = this->flowTrend.values();
    model.trendBucketSec = this->flowTrend.getBucketMs() / 1000UL;
    model.sensorLabel = "PULS";
    model.sensorOk = true;           // an open-collector contact can't report a cut cable
    model.raw = String(this->total / 1000.0, 3) + "m3";
    model.signal = String(this->pulseCount) + "p";
    if (this->flowExtremes.valid()) {
        model.low24 = this->flowExtremes.min();
        model.high24 = this->flowExtremes.max();
    }
    const double m3 = this->total / 1000.0;
    model.lines.push_back({"TOT", String(m3, m3 < 1000.0 ? 1 : 0) + "m3"});   // 5 digits still fit
    model.lines.push_back({"24H", String(this->usage24hLiters(), 0) + "L"});
    // Diagnostics: time since the last pulse (is the reader seeing the wheel?) and the 24 h peak
    // flow; the 24 h low of a household meter is always 0
    model.details.push_back({"LAST", this->anyPulse ? ageText(this->hal->millis() - this->lastPulseMs) : String("--")});
    model.details.push_back({"MAX", this->flowExtremes.valid() ? String(this->flowExtremes.max(), 1) + "L/m" : String("--")});
    return true;
}

bool PulseMeterPlugin::getChartData(std::vector<float>& points, int& spanSeconds) const
{
    const long bar = (long)(this->hal->millis() / HISTORY_BAR_MS);
    points.clear();
    for (long slot = bar - HISTORY_BARS + 1; slot <= bar; slot++) {
        if (slot < 0) continue;
        const int i = (int)(slot % HISTORY_BARS);
        points.push_back(this->barSlot[i] == slot ? this->barLiters[i] : 0.0f);
    }
    spanSeconds = (int)(HISTORY_BAR_MS / 1000UL);
    return !points.empty();
}

// --- MQTT ---

void PulseMeterPlugin::publishMqtt(MQTTClient& client, const String& baseTopic)
{
    JsonDocument doc;
    doc["total_m3"] = this->total / 1000.0;
    doc["total_l"] = this->total;
    doc["flow_rate"] = this->flow;
    doc["usage_24h"] = this->usage24hLiters();
    doc["continuous_h"] = this->continuousFlowHours();
    doc["pulses"] = this->pulseCount;
    doc["leak"] = this->leak();
    HaDiscovery::publishJson(client, baseTopic, doc);
}

static void totalIncreasing(JsonDocument& doc, const HaDiscoveryContext&)
{
    doc["state_class"] = "total_increasing";   // HA energy dashboard: water / gas consumption
}

void PulseMeterPlugin::publishHomeAssistantAutoconfig(MQTTClient& client, const HaDiscoveryContext& ctx)
{
    const Medium& m = *this->medium;
    const String noun = m.noun;
    const String device = "ESP " + noun + " Meter";
    const char* deviceName = ctx.nameOr(device.c_str());
    const String totalName = noun + " Meter", flowName = noun + " Flow", usageName = noun + " Usage 24h",
                 leakName = noun + " Continuous Flow";
    const HaEntity total = {"sensor", "total", "total", totalName.c_str(),
                            "{{ (value_json.total_m3 | float) | round(3) }}", "m\xC2\xB3", m.deviceClass, m.icon, false, false};
    HaDiscovery::publish(client, ctx, total, deviceName, totalIncreasing);
    const HaEntity entities[] = {
        {"sensor", "flow", "flow", flowName.c_str(), "{{ (value_json.flow_rate | float) | round(1) }}", "L/min", "volume_flow_rate", "mdi:speedometer", true, false},
        {"sensor", "usage_24h", "usage_24h", usageName.c_str(), "{{ value_json.usage_24h | round(0) }}", "L", m.deviceClass, "mdi:chart-bar", false, false},
        {"binary_sensor", "leak", "leak", leakName.c_str(), "{{ 'ON' if value_json.leak else 'OFF' }}", nullptr, m.leakClass, nullptr, false, false},
    };
    for (const HaEntity& entity : entities) HaDiscovery::publish(client, ctx, entity, deviceName);
}
