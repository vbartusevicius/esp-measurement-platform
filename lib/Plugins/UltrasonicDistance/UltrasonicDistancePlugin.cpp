#include "UltrasonicDistancePlugin.h"
#include <ESP8266WiFi.h>
#include "TimeHelper.h"

const char* UltrasonicDistancePlugin::getId() const { return "ultrasonic_distance"; }
const char* UltrasonicDistancePlugin::getName() const { return "Ultrasonic Distance Meter"; }

void UltrasonicDistancePlugin::setup(Storage* storage, Logger* logger, LedController* led)
{
    this->storage = storage;
    this->logger = logger;
    this->speedOfSound = 331.3 * sqrt(1 + (CURRENT_TEMP / ABSOLUTE_TEMP));
    this->measuredDistance = 0.0;
    this->relativeDistance = 0.0;
    this->absoluteDistance = 0.0;
    this->sensorConnected = false;

    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT_PULLUP);
}

void UltrasonicDistancePlugin::loop()
{
    float raw = this->readSensor();
    this->measuredDistance = this->aggregate(raw);
    this->relativeDistance = this->getRelative(this->measuredDistance);
    this->absoluteDistance = this->getAbsolute(this->measuredDistance);
}

// --- Sensor ---

float UltrasonicDistancePlugin::readSensor()
{
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(20);
    digitalWrite(TRIG_PIN, LOW);

    unsigned long pulse = pulseIn(ECHO_PIN, HIGH, 100000);
    double timeTook = (double)pulse / 1000000;
    float distance = this->speedOfSound * timeTook / 2;

    this->sensorConnected = (distance > 0.0);
    this->logger->info("Ultrasonic read: dist=" + String(distance, 3) + "m");

    return distance;
}

// --- Distance calculation ---

float UltrasonicDistancePlugin::getAbsolute(float distance)
{
    float emptyDist = atof(this->storage->getParameter(PARAM_DISTANCE_EMPTY).c_str()) / 100.0;
    float absolute = emptyDist - distance;
    return (absolute < 0) ? 0.0 : absolute;
}

float UltrasonicDistancePlugin::getRelative(float distance)
{
    float emptyDist = atof(this->storage->getParameter(PARAM_DISTANCE_EMPTY).c_str()) / 100.0;
    float fullDist = atof(this->storage->getParameter(PARAM_DISTANCE_FULL).c_str()) / 100.0;
    float denominator = emptyDist - fullDist;
    if (denominator == 0) return 0.0;
    return this->getAbsolute(distance) / denominator;
}

// --- Aggregation (same logic as analog) ---

float UltrasonicDistancePlugin::aggregate(float value)
{
    int window = atoi(this->storage->getParameter(PARAM_AVG_SAMPLE_COUNT, "10").c_str());
    int maxDelta = atoi(this->storage->getParameter(PARAM_MAX_DELTA, "15").c_str());

    float lastValue = this->avgBuffer.empty() ? 0.0 : this->avgBuffer.back();

    if ((int)this->avgBuffer.size() >= window) {
        this->avgBuffer.erase(this->avgBuffer.begin());
    }

    float diff = abs(lastValue - value);
    bool deltaOK = value * (maxDelta / 100.0) > diff || this->avgBuffer.empty();
    bool valueOK = round(value * 100.0) > 0;

    if (deltaOK && valueOK) {
        this->avgBuffer.push_back(value);
    }

    return this->calculateAverage();
}

float UltrasonicDistancePlugin::calculateAverage()
{
    if (this->avgBuffer.empty()) return 0.0;
    float sum = 0.0;
    for (auto& v : this->avgBuffer) sum += v;
    return sum / this->avgBuffer.size();
}

// --- Parameters ---

void UltrasonicDistancePlugin::getParameterDefs(std::vector<ParameterDef>& defs) const
{
    defs.push_back({PARAM_DISTANCE_EMPTY, "Empty Distance (cm)", "200", ParameterDef::NUMBER, true});
    defs.push_back({PARAM_DISTANCE_FULL, "Full Distance (cm)", "20", ParameterDef::NUMBER, true});
    defs.push_back({PARAM_AVG_SAMPLE_COUNT, "AVG Window Samples", "10", ParameterDef::NUMBER, false});
    defs.push_back({PARAM_SAMPLING_INTERVAL, "Sampling Interval (s)", "10", ParameterDef::NUMBER, false});
    defs.push_back({PARAM_MAX_DELTA, "Max Measurement Delta (%)", "15", ParameterDef::NUMBER, false});
}

std::vector<const char*> UltrasonicDistancePlugin::getRequiredParameters() const
{
    return {PARAM_DISTANCE_EMPTY, PARAM_DISTANCE_FULL};
}

// --- Stats ---

void UltrasonicDistancePlugin::getStats(JsonDocument& doc) const
{
    doc["measured_distance"] = this->measuredDistance;
    doc["relative_distance"] = this->relativeDistance;
    doc["absolute_distance"] = this->absoluteDistance;
    doc["sensor_connected"] = this->sensorConnected;
}

// --- MQTT ---

void UltrasonicDistancePlugin::publishMqtt(MQTTClient& client, const String& baseTopic)
{
    JsonDocument doc;
    String json;

    doc["relative"] = this->relativeDistance;
    doc["absolute"] = this->absoluteDistance;
    doc["measured"] = this->measuredDistance;
    serializeJson(doc, json);

    client.publish(baseTopic.c_str(), json.c_str(), false, 0);
}

void UltrasonicDistancePlugin::publishHomeAssistantAutoconfig(MQTTClient& client, const String& deviceId, const String& stateTopic)
{
    JsonDocument doc;
    doc["state_topic"] = stateTopic;
    doc["value_template"] = "{{ ((value_json.relative | float) * 100) | round(2) }}";
    doc["unit_of_measurement"] = "%";
    doc["name"] = "ESP Ultrasonic Distance";
    doc["unique_id"] = deviceId + "_distance";
    doc["object_id"] = "esp_ultrasonic_distance";

    JsonObject device = doc["device"].to<JsonObject>();
    device["identifiers"][0] = deviceId;
    device["name"] = "ESP Ultrasonic Distance Meter";
    device["model"] = "ESP8266";
    device["manufacturer"] = "ESP";

    String json;
    serializeJson(doc, json);
    client.publish(("homeassistant/sensor/" + deviceId + "/config").c_str(), json.c_str(), true, 1);
}

// --- Display (same layout as analog) ---

int UltrasonicDistancePlugin::getDisplayPageCount() const { return 1; }

int UltrasonicDistancePlugin::getSamplingInterval() const
{
    String interval = this->storage->getParameter(PARAM_SAMPLING_INTERVAL, "10");
    int val = interval.toInt();
    return val < 1 ? 1 : val;
}

void UltrasonicDistancePlugin::renderDisplayPage(U8G2& u8g2, int page, int width, int height) const
{
    int cursorY = 0;

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
    cursorY = barHeight;

    // Network info
    u8g2.setDrawColor(1);
    u8g2.setFontMode(0);

    int rssi = WiFi.RSSI();
    unsigned int glyph = 57887;
    if (rssi >= -95) glyph = 57888;
    if (rssi >= -85) glyph = 57889;
    if (rssi >= -75) glyph = 57890;

    u8g2.setFont(u8g2_font_siji_t_6x10);
    u8g2.drawGlyph(width - 10, cursorY + 14, glyph);

    u8g2.setFont(u8g2_font_5x7_tr);
    u8g2.drawStr(0, cursorY + 7, ("SSID: " + WiFi.SSID()).c_str());
    u8g2.drawStr(0, cursorY + 15, ("IP: " + WiFi.localIP().toString()).c_str());
    u8g2.drawHLine(0, cursorY + 16, width);
    cursorY += 17;

    // Sensor / MQTT statuses
    const char* sGlyph = this->sensorConnected ? "[+]" : "[ ]";
    u8g2.setFont(u8g2_font_5x7_tr);
    u8g2.drawStr(0, cursorY + 8, "Sensor:");
    int gw = u8g2.getStrWidth(sGlyph);
    u8g2.drawStr((width / 2) - gw, cursorY + 8, sGlyph);
    cursorY += 8;

    char uptimeBuf[32];
    TimeHelper::getUptime(uptimeBuf);
    u8g2.drawStr(0, cursorY + 8, "Uptime:");
    u8g2.drawStr(49, cursorY + 8, uptimeBuf);
}
