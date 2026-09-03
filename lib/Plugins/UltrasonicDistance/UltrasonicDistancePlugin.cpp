#include "UltrasonicDistancePlugin.h"
#include <ArduinoJson.h>
#include "UltrasonicDistanceCalculator.h"
#include "HAL.h"

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
    this->logger->info("Ultrasonic read: dist=" + String(distance, 3) + "m");

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

void UltrasonicDistancePlugin::publishHomeAssistantAutoconfig(MQTTClient& client, const String& deviceId, const String& stateTopic)
{
    {
        JsonDocument doc;
        doc["state_topic"] = stateTopic;
        doc["value_template"] = "{{ ((value_json.relative | float) * 100) | round(2) }}";
        doc["unit_of_measurement"] = "%";
        doc["name"] = "ESP Ultrasonic Distance";
        doc["unique_id"] = deviceId + "_distance";
        doc["object_id"] = "esp_ultrasonic_distance";

        JsonObject device = doc["device"].to<JsonObject>();
        this->addHaDevice(device, deviceId);

        String json;
        serializeJson(doc, json);
        client.publish(("homeassistant/sensor/" + deviceId + "/config").c_str(), json.c_str(), true, 1);
    }

    // Flow rate sensor (L/min)
    this->publishFlowRateHaConfig(client, deviceId, stateTopic);
}
