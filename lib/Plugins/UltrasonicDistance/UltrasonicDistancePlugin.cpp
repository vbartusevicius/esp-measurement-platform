#include "UltrasonicDistancePlugin.h"
#include "HAL.h"

const char* UltrasonicDistancePlugin::getId() const { return "ultrasonic_distance"; }
const char* UltrasonicDistancePlugin::getName() const { return "Ultrasonic Distance Meter"; }

void UltrasonicDistancePlugin::setup(HAL* hal, Storage* storage, Logger* logger, LedController* led)
{
    this->hal = hal;
    this->storage = storage;
    this->logger = logger;
    this->speedOfSound = 331.3 * sqrt(1 + (CURRENT_TEMP / ABSOLUTE_TEMP));
    this->measuredDistance = 0.0;
    this->relativeDistance = 0.0;
    this->absoluteDistance = 0.0;
    this->sensorConnected = false;
    this->distCalc.reset();

    this->hal->pinMode(TRIG_PIN, OUTPUT);
    this->hal->pinMode(ECHO_PIN, INPUT_PULLUP);
}

void UltrasonicDistancePlugin::loop()
{
    float raw = this->readSensor();

    int window = atoi(this->storage->getParameter(PARAM_AVG_SAMPLE_COUNT, "10").c_str());
    int maxDelta = atoi(this->storage->getParameter(PARAM_MAX_DELTA, "15").c_str());
    this->measuredDistance = this->distCalc.aggregate(raw, window, maxDelta);

    float emptyDist = atof(this->storage->getParameter(PARAM_DISTANCE_EMPTY).c_str()) / 100.0;
    float fullDist = atof(this->storage->getParameter(PARAM_DISTANCE_FULL).c_str()) / 100.0;
    this->relativeDistance = UltrasonicDistanceCalculator::getRelative(this->measuredDistance, emptyDist, fullDist);
    this->absoluteDistance = UltrasonicDistanceCalculator::getAbsolute(this->measuredDistance, emptyDist);
}

// --- Sensor ---

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

void UltrasonicDistancePlugin::getStats(std::vector<StatEntry>& entries) const
{
    entries.push_back({"Level", String(this->relativeDistance * 100, 1) + "%", this->relativeDistance, StatEntry::PROGRESS, true});
    entries.push_back({"Depth", String(this->absoluteDistance, 2) + " m", this->absoluteDistance, StatEntry::TEXT, true});
    entries.push_back({"Distance", String(this->measuredDistance, 3) + " m", this->measuredDistance, StatEntry::TEXT, false});
    entries.push_back({"Sensor", this->sensorConnected ? "Connected" : "Disconnected", this->sensorConnected ? 1.0f : 0.0f, StatEntry::TEXT, false});
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

int UltrasonicDistancePlugin::renderDisplayPage(U8G2& u8g2, int page, int width, int height) const
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
    const char* sGlyph = this->sensorConnected ? "[+]" : "[ ]";
    u8g2.setFont(u8g2_font_5x7_tr);
    u8g2.drawStr(0, cursorY + 8, "Sensor:");
    int gw = u8g2.getStrWidth(sGlyph);
    u8g2.drawStr((width / 2) - gw, cursorY + 8, sGlyph);
    cursorY += 8;

    return cursorY;
}
