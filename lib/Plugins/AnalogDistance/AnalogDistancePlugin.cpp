#include "AnalogDistancePlugin.h"

const char* AnalogDistancePlugin::getId() const { return "analog_distance"; }
const char* AnalogDistancePlugin::getName() const { return "Analog Distance Meter"; }

void AnalogDistancePlugin::setup(Storage* storage, Logger* logger, LedController* led)
{
    this->storage = storage;
    this->logger = logger;
    this->measuredDistance = 0.0;
    this->relativeDistance = 0.0;
    this->absoluteDistance = 0.0;
    this->sensorConnected = false;

    pinMode(ANALOG_PIN, INPUT);
}

void AnalogDistancePlugin::loop()
{
    float raw = this->readSensor();
    this->measuredDistance = this->aggregate(raw);
    this->relativeDistance = this->getRelative(this->measuredDistance);
    this->absoluteDistance = this->getAbsolute(this->measuredDistance);
}

// --- Sensor reading ---

float AnalogDistancePlugin::readSensor()
{
    int rawValue = analogRead(ANALOG_PIN);
    float voltage = (rawValue / 1023.0) * VOLTAGE_REF;

    this->sensorConnected = isSensorConnected(voltage);
    float distance = 0.0;

    if (this->sensorConnected) {
        distance = voltageToDistance(voltage);
    }

    float current = voltageToCurrentMA(voltage);
    this->logger->info("Analog read: raw=" + String(rawValue) + " V=" + String(voltage, 2) +
                       " mA=" + String(current, 2) + " dist=" + String(distance, 3) + "m" +
                       " sensor=" + String(this->sensorConnected ? "ok" : "fault"));
    return distance;
}

float AnalogDistancePlugin::voltageToCurrentMA(float voltage)
{
    return MIN_CURRENT_MA + (voltage / VOLTAGE_REF) * (MAX_CURRENT_MA - MIN_CURRENT_MA);
}

float AnalogDistancePlugin::voltageToDistance(float voltage)
{
    float sensorRange = atof(this->storage->getParameter(PARAM_SENSOR_RANGE, "5").c_str());
    float current = voltageToCurrentMA(voltage);
    return ((current - MIN_CURRENT_MA) / (MAX_CURRENT_MA - MIN_CURRENT_MA)) * sensorRange;
}

bool AnalogDistancePlugin::isSensorConnected(float voltage)
{
    return voltageToCurrentMA(voltage) >= FAULT_CURRENT_MA;
}

// --- Distance calculation ---

float AnalogDistancePlugin::getRelative(float sensorToWaterDistance)
{
    float emptyDist = atof(this->storage->getParameter(PARAM_DISTANCE_EMPTY).c_str()) / 100.0;
    float fullDist = atof(this->storage->getParameter(PARAM_DISTANCE_FULL).c_str()) / 100.0;

    if (sensorToWaterDistance <= emptyDist) return 0.0;
    if (sensorToWaterDistance >= fullDist) return 1.0;
    return (sensorToWaterDistance - emptyDist) / (fullDist - emptyDist);
}

float AnalogDistancePlugin::getAbsolute(float sensorToWaterDistance)
{
    float relative = this->getRelative(sensorToWaterDistance);
    float maxDepth = atof(this->storage->getParameter(PARAM_DISTANCE_FULL).c_str()) / 100.0;
    return relative * maxDepth;
}

// --- Aggregation ---

float AnalogDistancePlugin::aggregate(float value)
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

float AnalogDistancePlugin::calculateAverage()
{
    if (this->avgBuffer.empty()) return 0.0;
    float sum = 0.0;
    for (auto& v : this->avgBuffer) sum += v;
    return sum / this->avgBuffer.size();
}

// --- Parameters ---

void AnalogDistancePlugin::getParameterDefs(std::vector<ParameterDef>& defs) const
{
    defs.push_back({PARAM_SENSOR_RANGE, "Sensor Range (m)", "5", ParameterDef::NUMBER, true});
    defs.push_back({PARAM_DISTANCE_EMPTY, "Empty Reading (cm)", "10", ParameterDef::NUMBER, true});
    defs.push_back({PARAM_DISTANCE_FULL, "Full Reading (cm)", "100", ParameterDef::NUMBER, true});
    defs.push_back({PARAM_AVG_SAMPLE_COUNT, "AVG Window Samples", "10", ParameterDef::NUMBER, false});
    defs.push_back({PARAM_SAMPLING_INTERVAL, "Sampling Interval (s)", "10", ParameterDef::NUMBER, false});
    defs.push_back({PARAM_MAX_DELTA, "Max Measurement Delta (%)", "15", ParameterDef::NUMBER, false});
}

std::vector<const char*> AnalogDistancePlugin::getRequiredParameters() const
{
    return {PARAM_DISTANCE_EMPTY, PARAM_DISTANCE_FULL, PARAM_SENSOR_RANGE};
}

// --- Stats ---

void AnalogDistancePlugin::getStats(std::vector<StatEntry>& entries) const
{
    entries.push_back({"Level", String(this->relativeDistance * 100, 1) + "%", this->relativeDistance, StatEntry::PROGRESS, true});
    entries.push_back({"Depth", String(this->absoluteDistance, 2) + " m", this->absoluteDistance, StatEntry::TEXT, true});
    entries.push_back({"Distance", String(this->measuredDistance, 3) + " m", this->measuredDistance, StatEntry::TEXT, false});
    entries.push_back({"Sensor", this->sensorConnected ? "Connected" : "Disconnected", this->sensorConnected ? 1.0f : 0.0f, StatEntry::TEXT, false});
}

// --- MQTT ---

void AnalogDistancePlugin::publishMqtt(MQTTClient& client, const String& baseTopic)
{
    JsonDocument doc;
    String json;

    doc["relative"] = this->relativeDistance;
    doc["absolute"] = this->absoluteDistance;
    doc["measured"] = this->measuredDistance;
    serializeJson(doc, json);

    client.publish(baseTopic.c_str(), json.c_str(), false, 0);
}

void AnalogDistancePlugin::publishHomeAssistantAutoconfig(MQTTClient& client, const String& deviceId, const String& stateTopic)
{
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
        device["identifiers"][0] = deviceId;
        device["name"] = "ESP Analog Distance Meter";
        device["model"] = "ESP8266";
        device["manufacturer"] = "ESP";

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
        device["identifiers"][0] = deviceId;
        device["name"] = "ESP Analog Distance Meter";
        device["model"] = "ESP8266";
        device["manufacturer"] = "ESP";

        String json;
        serializeJson(doc, json);
        client.publish(("homeassistant/sensor/" + deviceId + "/depth/config").c_str(), json.c_str(), true, 1);
    }
}

// --- Display ---

int AnalogDistancePlugin::getDisplayPageCount() const { return 1; }

int AnalogDistancePlugin::getSamplingInterval() const
{
    String interval = this->storage->getParameter(PARAM_SAMPLING_INTERVAL, "10");
    int val = interval.toInt();
    return val < 1 ? 1 : val;
}

int AnalogDistancePlugin::renderDisplayPage(U8G2& u8g2, int page, int width, int height) const
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
    const char* sensorGlyph = this->sensorConnected ? "[+]" : "[ ]";
    u8g2.setFont(u8g2_font_5x7_tr);
    u8g2.drawStr(0, cursorY + 8, "Sensor:");
    int gw = u8g2.getStrWidth(sensorGlyph);
    u8g2.drawStr((width / 2) - gw, cursorY + 8, sensorGlyph);
    cursorY += 8;

    return cursorY;
}
