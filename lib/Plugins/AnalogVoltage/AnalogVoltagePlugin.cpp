#include "AnalogVoltagePlugin.h"
#include <cstring>
#include "AnalogVoltageConverter.h"
#include "HAL.h"
#include "Logger.h"
#include "Settings.h"

static bool isPressureUnit(const char* unit)
{
    static const char* units[] = {"bar", "mbar", "cbar", "kPa", "hPa", "Pa", "MPa", "psi", "mmHg", "inHg"};
    for (const char* candidate : units) {
        if (strcmp(unit, candidate) == 0) return true;
    }
    return false;
}

const char* AnalogVoltagePlugin::getId() const { return "analog_voltage"; }
const char* AnalogVoltagePlugin::getName() const { return "Pressure / 0-10 V Sensor"; }

void AnalogVoltagePlugin::setup(HAL* hal, Settings* storage, Logger* logger, LedController* led)
{
    this->hal = hal;
    this->storage = storage;
    this->logger = logger;

    this->voltageMin = this->storage->getParameter(PARAM_VOLTAGE_MIN, "0.5").toFloat();
    this->voltageMax = this->storage->getParameter(PARAM_VOLTAGE_MAX, "4.5").toFloat();
    this->valueMin = this->storage->getParameter(PARAM_VALUE_MIN, "0").toFloat();
    this->valueMax = this->storage->getParameter(PARAM_VALUE_MAX, "10").toFloat();
    this->unit = this->storage->getParameter(PARAM_VALUE_UNIT, "bar");
    this->title = this->storage->getParameter(PARAM_TITLE, "PRES");
    if (this->title.length() > 4) this->title = this->title.substring(0, 4);
    this->decimals = this->storage->getParameter(PARAM_DECIMALS, "1").toInt();
    if (this->decimals < 0) this->decimals = 0;
    if (this->decimals > 3) this->decimals = 3;
    int interval = this->storage->getParameter(PARAM_SAMPLING_INTERVAL, "5").toInt();
    this->samplingIntervalSec = interval < 1 ? 1 : interval;

    this->sampled = false;
    this->trend.reset();
    this->extremes.reset();
    this->history.reset();
    this->hal->pinMode(INPUT_PIN, INPUT);
}

void AnalogVoltagePlugin::loop()
{
    long sum = 0;
    for (int i = 0; i < OVERSAMPLE; i++) sum += this->hal->analogReadMilliVolts(INPUT_PIN);
    this->inputVolts = AnalogVoltageConverter::pinToInputVolts((int)(sum / OVERSAMPLE), DIVIDER);
    this->sensorConnected = AnalogVoltageConverter::isConnected(this->inputVolts, this->voltageMin, this->voltageMax);
    this->value = AnalogVoltageConverter::scale(this->inputVolts, this->voltageMin, this->voltageMax, this->valueMin, this->valueMax);
    this->sampled = true;

    if (this->sensorConnected) {
        const unsigned long now = this->hal->millis();
        this->trend.add(this->value, now);
        this->extremes.update(this->value, now);
        this->history.add(this->value, now);
    }
    this->logger->debug("Voltage read: V=" + String(this->inputVolts, 3) + " value=" + String(this->value, this->decimals) +
                        " sensor=" + String(this->sensorConnected ? "ok" : "fault"));
}

void AnalogVoltagePlugin::getParameterDefs(std::vector<ParameterDef>& defs) const
{
    defs.push_back({PARAM_VOLTAGE_MIN, "Sensor Output at Min (V)", "0.5", ParameterDef::NUMBER, true});
    defs.push_back({PARAM_VOLTAGE_MAX, "Sensor Output at Max (V)", "4.5", ParameterDef::NUMBER, true});
    defs.push_back({PARAM_VALUE_MIN, "Value at Min", "0", ParameterDef::NUMBER, true});
    defs.push_back({PARAM_VALUE_MAX, "Value at Max", "10", ParameterDef::NUMBER, true});
    defs.push_back({PARAM_VALUE_UNIT, "Unit (bar, psi, kPa, V...)", "bar", ParameterDef::TEXT, false});
    defs.push_back({PARAM_DECIMALS, "Decimals", "1", ParameterDef::NUMBER, false});
    defs.push_back({PARAM_TITLE, "Display Title (4 chars)", "PRES", ParameterDef::TEXT, false});
    defs.push_back({PARAM_SAMPLING_INTERVAL, "Sampling Interval (s)", "5", ParameterDef::NUMBER, false});
}

void AnalogVoltagePlugin::getStats(std::vector<StatEntry>& entries) const
{
    entries.push_back({"value", "Value", String(this->value, this->decimals) + " " + this->unit, this->value});
    entries.push_back({"voltage", "Input", String(this->inputVolts, 3) + " V", this->inputVolts});
    entries.push_back({"sensor", "Sensor", this->sensorConnected ? "Connected" : "Disconnected", this->sensorConnected ? 1.0f : 0.0f});
}

bool AnalogVoltagePlugin::getScreen(ScreenModel& model) const
{
    model.kind = isPressureUnit(this->unit.c_str()) ? "pressure" : "voltage";
    model.title = this->title.c_str();
    model.value = this->value;
    model.unit = this->unit.c_str();
    model.decimals = this->decimals;
    model.valid = this->sampled && this->sensorConnected;
    model.scaleMin = this->valueMin;
    model.scaleMax = this->valueMax;
    model.trend = this->trend.values();
    model.trendBucketSec = this->trend.getBucketMs() / 1000UL;
    model.sensorLabel = "SENS";
    model.sensorOk = this->sensorConnected;
    model.raw = String(this->value, this->decimals + 1) + this->unit;
    model.signal = String(this->inputVolts, 2) + "V";
    if (this->extremes.valid()) {
        model.low24 = this->extremes.min();
        model.high24 = this->extremes.max();
    }
    model.lines.push_back({"IN", String(this->inputVolts, 2) + "V"});
    model.lines.push_back({"RNG", String(this->valueMax, 0) + this->unit});
    return true;
}

bool AnalogVoltagePlugin::getChartData(std::vector<float>& points, int& spanSeconds) const
{
    points = this->history.values();
    spanSeconds = (int)(this->history.getBucketMs() / 1000UL);
    return true;
}

void AnalogVoltagePlugin::publishMqtt(MQTTClient& client, const String& baseTopic)
{
    JsonDocument doc;
    doc["value"] = this->value;
    doc["voltage"] = this->inputVolts;
    doc["connected"] = this->sensorConnected;
    HaDiscovery::publishJson(client, baseTopic, doc);
}

void AnalogVoltagePlugin::publishHomeAssistantAutoconfig(MQTTClient& client, const HaDiscoveryContext& ctx)
{
    const char* deviceName = ctx.nameOr("ESP Pressure Sensor");
    const String valueTemplate = "{{ (value_json.value | float) | round(" + String(this->decimals) + ") }}";
    const HaEntity value = {"sensor", "value", "value", this->title.c_str(), valueTemplate.c_str(), this->unit.c_str(),
                            isPressureUnit(this->unit.c_str()) ? "pressure" : nullptr, "mdi:gauge", true, false};
    static const HaEntity diagnostics[] = {
        {"sensor", "voltage", "voltage", "Sensor Voltage", "{{ (value_json.voltage | float) | round(3) }}", "V", "voltage", nullptr, true, true},
        {"binary_sensor", "connected", "connected", "Sensor", "{{ 'ON' if value_json.connected else 'OFF' }}", nullptr, "connectivity", nullptr, false, true},
    };
    HaDiscovery::publish(client, ctx, value, deviceName);
    for (const HaEntity& entity : diagnostics) HaDiscovery::publish(client, ctx, entity, deviceName);
}
