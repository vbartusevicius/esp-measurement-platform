#include "UltrasonicDistancePlugin.h"
#include <cmath>
#include "HAL.h"
#include "Logger.h"
#include "UltrasonicDistanceCalculator.h"

const char* UltrasonicDistancePlugin::getId() const { return "ultrasonic_distance"; }
const char* UltrasonicDistancePlugin::getName() const { return "Ultrasonic Distance Meter"; }
const char* UltrasonicDistancePlugin::getDeviceName() const { return "ESP Ultrasonic Distance Meter"; }

void UltrasonicDistancePlugin::setup(HAL* hal, Storage* storage, Logger* logger, LedController* led)
{
    DistancePluginBase::setup(hal, storage, logger, led);
    this->speedOfSound = 331.3 * sqrt(1 + (CURRENT_TEMP / ABSOLUTE_TEMP));
}

void UltrasonicDistancePlugin::setupPins()
{
    this->hal->pinMode(TRIG_PIN, OUTPUT);
    this->hal->pinMode(ECHO_PIN, INPUT_PULLUP);
}

float UltrasonicDistancePlugin::readSensor()
{
    this->hal->digitalWrite(TRIG_PIN, LOW);
    this->hal->delayMicroseconds(2);
    this->hal->digitalWrite(TRIG_PIN, HIGH);
    this->hal->delayMicroseconds(20);
    this->hal->digitalWrite(TRIG_PIN, LOW);

    unsigned long pulse = this->hal->pulseIn(ECHO_PIN, HIGH, 100000);
    double timeTook = (double)pulse / 1000000;
    float distance = this->speedOfSound * timeTook / 2;

    this->sensorConnected = (distance > 0.0);
    this->lastSignal = String((unsigned long)pulse) + "us";
    this->logger->debug("Ultrasonic read: dist=" + String(distance, 3) + "m");

    return distance;
}

float UltrasonicDistancePlugin::computeRelative(float measured, float emptyDist, float fullDist) const
{
    return UltrasonicDistanceCalculator::getRelative(measured, emptyDist, fullDist);
}

float UltrasonicDistancePlugin::computeAbsolute(float measured, float emptyDist, float fullDist) const
{
    return UltrasonicDistanceCalculator::getAbsolute(measured, emptyDist);
}

// --- Parameters ---

void UltrasonicDistancePlugin::addPluginParameterDefs(std::vector<ParameterDef>& defs) const
{
    defs.push_back({PARAM_DISTANCE_EMPTY, "Empty Distance (cm)", "200", ParameterDef::NUMBER, true});
    defs.push_back({PARAM_DISTANCE_FULL, "Full Distance (cm)", "20", ParameterDef::NUMBER, true});
}

// --- Home Assistant discovery ---

void UltrasonicDistancePlugin::publishHomeAssistantAutoconfig(MQTTClient& client, const HaDiscoveryContext& ctx)
{
    // Legacy entity (topic without object id, fixed object_id) kept for existing installs.
    static const HaEntity level =
        {"sensor", "", "distance", "ESP Ultrasonic Distance", "{{ ((value_json.relative | float) * 100) | round(2) }}", "%", nullptr, nullptr, false, false};
    HaDiscovery::publish(client, ctx, level, ctx.nameOr(this->getDeviceName()),
                         [](JsonDocument& doc, const HaDiscoveryContext&) { doc["object_id"] = "esp_ultrasonic_distance"; });
    this->publishCommonHaSensors(client, ctx);
}
