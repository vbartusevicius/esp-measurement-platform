#include "AnalogDistancePlugin.h"
#include <ArduinoJson.h>
#include "HaDiscovery.h"
#include "AnalogDistanceCalculator.h"
#include "AnalogSensorConverter.h"
#include "HAL.h"

const char* AnalogDistancePlugin::getId() const { return "analog_distance"; }
const char* AnalogDistancePlugin::getName() const { return "Analog Distance Meter"; }
const char* AnalogDistancePlugin::getDeviceName() const { return "ESP Analog Distance Meter"; }

void AnalogDistancePlugin::setupPins()
{
    this->hal->pinMode(ANALOG_PIN, INPUT);
}

void AnalogDistancePlugin::loadPluginConfig()
{
    this->sensorRange = atof(this->storage->getParameter(PARAM_SENSOR_RANGE, "5").c_str());
}

float AnalogDistancePlugin::readSensor()
{
    int rawValue = this->hal->analogRead(ANALOG_PIN);
    float voltage = (rawValue / 1023.0) * VOLTAGE_REF;

    float current = AnalogSensorConverter::voltageToCurrentMA(voltage, VOLTAGE_REF, MIN_CURRENT_MA, MAX_CURRENT_MA);
    this->sensorConnected = AnalogSensorConverter::isSensorConnected(current, FAULT_CURRENT_MA);
    float distance = 0.0;

    if (this->sensorConnected) {
        distance = AnalogSensorConverter::currentToDistance(current, MIN_CURRENT_MA, MAX_CURRENT_MA, this->sensorRange);
    }

    this->logger->debug("Analog read: raw=" + String(rawValue) + " V=" + String(voltage, 2) +
                       " mA=" + String(current, 2) + " dist=" + String(distance, 3) + "m" +
                       " sensor=" + String(this->sensorConnected ? "ok" : "fault"));
    return distance;
}

float AnalogDistancePlugin::computeRelative(float measured, float emptyDist, float fullDist) const
{
    return AnalogDistanceCalculator::getRelative(measured, emptyDist, fullDist);
}

float AnalogDistancePlugin::computeAbsolute(float measured, float emptyDist, float fullDist) const
{
    return AnalogDistanceCalculator::getAbsolute(measured, emptyDist, fullDist);
}

// --- Parameters ---

void AnalogDistancePlugin::addPluginParameterDefs(std::vector<ParameterDef>& defs) const
{
    defs.push_back({PARAM_SENSOR_RANGE, "Sensor Range (m)", "5", ParameterDef::NUMBER, true});
    defs.push_back({PARAM_DISTANCE_EMPTY, "Empty Reading (cm)", "10", ParameterDef::NUMBER, true});
    defs.push_back({PARAM_DISTANCE_FULL, "Full Reading (cm)", "100", ParameterDef::NUMBER, true});
}

// --- Home Assistant discovery ---

void AnalogDistancePlugin::publishHomeAssistantAutoconfig(MQTTClient& client, const HaDiscoveryContext& ctx)
{
    const String& deviceId = ctx.deviceId;
    const String& stateTopic = ctx.stateTopic;

    // Level sensor (percentage)
    {
        JsonDocument doc;
        doc["state_topic"] = stateTopic;
        doc["value_template"] = "{{ ((value_json.relative | float) * 100) | round(1) }}";
        doc["unit_of_measurement"] = "%";
        doc["name"] = "Water Level";
        doc["unique_id"] = deviceId + "_level";
        doc["icon"] = "mdi:water-percent";
        doc["state_class"] = "measurement";

        JsonObject device = doc["device"].to<JsonObject>();
        HaDiscovery::addDeviceInfo(device, deviceId, this->getDeviceName());
        HaDiscovery::addAvailability(doc, ctx.availabilityTopic);

        String json;
        serializeJson(doc, json);
        client.publish(("homeassistant/sensor/" + deviceId + "/level/config").c_str(), json.c_str(), true, 1);
    }

    // Depth sensor (meters)
    {
        JsonDocument doc;
        doc["state_topic"] = stateTopic;
        doc["value_template"] = "{{ value_json.absolute | round(2) }}";
        doc["unit_of_measurement"] = "m";
        doc["name"] = "Water Depth";
        doc["unique_id"] = deviceId + "_depth";
        doc["device_class"] = "distance";
        doc["icon"] = "mdi:ruler";
        doc["state_class"] = "measurement";

        JsonObject device = doc["device"].to<JsonObject>();
        HaDiscovery::addDeviceInfo(device, deviceId, this->getDeviceName());
        HaDiscovery::addAvailability(doc, ctx.availabilityTopic);

        String json;
        serializeJson(doc, json);
        client.publish(("homeassistant/sensor/" + deviceId + "/depth/config").c_str(), json.c_str(), true, 1);
    }

    // Flow rate sensor (L/min)
    this->publishCommonHaSensors(client, ctx);
}
