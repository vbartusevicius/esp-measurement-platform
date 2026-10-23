#include "AnalogVoltagePlugin.h"
#include <ArduinoJson.h>
#include <cstring>
#include "AnalogVoltageConverter.h"
#include "HaDiscovery.h"
#include "HAL.h"

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

void AnalogVoltagePlugin::setup(HAL* hal, Storage* storage, Logger* logger, LedController* led)
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
        this->trend.add(this->value, this->hal->millis());
        this->extremes.update(this->value, this->hal->millis());
        this->history.add(this->value, this->hal->millis());
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
    entries.push_back({"Value", String(this->value, this->decimals) + " " + this->unit, this->value, StatEntry::TEXT, true, "value"});
    entries.push_back({"Input", String(this->inputVolts, 3) + " V", this->inputVolts, StatEntry::TEXT, false, "voltage"});
    entries.push_back({"Sensor", this->sensorConnected ? "Connected" : "Disconnected", this->sensorConnected ? 1.0f : 0.0f, StatEntry::TEXT, false, "sensor"});
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
    String json;
    serializeJson(doc, json);
    client.publish(baseTopic.c_str(), json.c_str(), false, 0);
}

void AnalogVoltagePlugin::publishHomeAssistantAutoconfig(MQTTClient& client, const HaDiscoveryContext& ctx)
{
    const char* deviceName = ctx.nameOr("ESP Pressure Sensor");
    auto publish = [&](const char* component, const char* objectId, JsonDocument& doc) {
        doc["state_topic"] = ctx.stateTopic;
        doc["unique_id"] = ctx.deviceId + "_" + objectId;
        JsonObject device = doc["device"].to<JsonObject>();
        HaDiscovery::addDeviceInfo(device, ctx.deviceId, deviceName);
        HaDiscovery::addAvailability(doc, ctx.availabilityTopic);
        String json;
        serializeJson(doc, json);
        client.publish((String("homeassistant/") + component + "/" + ctx.deviceId + "/" + objectId + "/config").c_str(), json.c_str(), true, 1);
    };

    {
        JsonDocument doc;
        doc["name"] = this->title;
        doc["value_template"] = "{{ (value_json.value | float) | round(" + String(this->decimals) + ") }}";
        doc["unit_of_measurement"] = this->unit;
        if (isPressureUnit(this->unit.c_str())) doc["device_class"] = "pressure";
        doc["state_class"] = "measurement";
        doc["icon"] = "mdi:gauge";
        publish("sensor", "value", doc);
    }
    {
        JsonDocument doc;
        doc["name"] = "Sensor Voltage";
        doc["value_template"] = "{{ (value_json.voltage | float) | round(3) }}";
        doc["unit_of_measurement"] = "V";
        doc["device_class"] = "voltage";
        doc["state_class"] = "measurement";
        doc["entity_category"] = "diagnostic";
        publish("sensor", "voltage", doc);
    }
    {
        JsonDocument doc;
        doc["name"] = "Sensor";
        doc["value_template"] = "{{ 'ON' if value_json.connected else 'OFF' }}";
        doc["device_class"] = "connectivity";
        doc["entity_category"] = "diagnostic";
        publish("binary_sensor", "connected", doc);
    }
}

int AnalogVoltagePlugin::renderDisplayPage(U8G2& u8g2, int page, int width, int height) const
{
    u8g2.setFont(u8g2_font_6x12_mf);
    String text = this->sensorConnected ? String(this->value, this->decimals) + " " + this->unit : String("Sensor fault");
    u8g2.drawStr(0, 12, text.c_str());
    u8g2.setFont(u8g2_font_5x7_tr);
    u8g2.drawStr(0, 22, (String(this->inputVolts, 2) + " V").c_str());
    return 24;
}
