#include "AnalogDistancePlugin.h"
#include "AnalogDistanceCalculator.h"
#include "AnalogSensorConverter.h"
#include "HAL.h"
#include "Logger.h"
#include "Storage.h"

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
    const int millivolts = this->hal->analogReadMilliVolts(ANALOG_PIN);
    const float current = AnalogSensorConverter::shuntMillivoltsToCurrentMA(millivolts, SHUNT_OHMS);
    this->sensorConnected = AnalogSensorConverter::isSensorConnected(current, FAULT_CURRENT_MA);
    this->lastSignal = String(current, 1) + "mA";
    float distance = 0.0;

    if (this->sensorConnected) {
        distance = AnalogSensorConverter::currentToDistance(current, MIN_CURRENT_MA, MAX_CURRENT_MA, this->sensorRange);
    }

    this->logger->debug("Analog read: mV=" + String(millivolts) +
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
    static const HaEntity entities[] = {
        {"sensor", "level", "level", "Level", "{{ ((value_json.relative | float) * 100) | round(1) }}", "%", nullptr, "mdi:gauge", true, false},
        {"sensor", "depth", "depth", "Depth", "{{ value_json.absolute | round(2) }}", "m", "distance", "mdi:ruler", true, false},
    };
    for (const HaEntity& entity : entities) HaDiscovery::publish(client, ctx, entity, ctx.nameOr(this->getDeviceName()));
    this->publishCommonHaSensors(client, ctx);
}
