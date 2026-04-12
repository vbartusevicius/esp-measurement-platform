#include "RadiationCounterPlugin.h"

RadiationCounterPlugin* RadiationCounterPlugin::instance = nullptr;

void IRAM_ATTR RadiationCounterPlugin::radiationISR()
{
    if (instance) instance->onRadiationClick();
}

void IRAM_ATTR RadiationCounterPlugin::buttonISR()
{
    if (instance) instance->onButtonClick();
}

const char* RadiationCounterPlugin::getId() const { return "radiation_counter"; }
const char* RadiationCounterPlugin::getName() const { return "Radiation Counter Gateway"; }

void RadiationCounterPlugin::setup(Storage* storage, Logger* logger, LedController* led)
{
    this->storage = storage;
    this->logger = logger;
    this->led = led;

    this->clickCounter = 0;
    this->cpm = 0;
    this->dose = 0.0;
    this->spanPointer = 0;
    this->buttonCounter = 0;

    pinMode(CNT_PIN, INPUT);
    pinMode(BTN_PIN, INPUT);

    instance = this;
    attachInterrupt(digitalPinToInterrupt(CNT_PIN), radiationISR, CHANGE);
    attachInterrupt(digitalPinToInterrupt(BTN_PIN), buttonISR, CHANGE);
    logger->info("Radiation counter interrupts attached");
}

void RadiationCounterPlugin::onRadiationClick()
{
    int pinState = digitalRead(CNT_PIN);
    if (pinState == HIGH) {
        this->clickCounter++;
        if (this->led) this->led->click();
    }
}

void RadiationCounterPlugin::onButtonClick()
{
    int pinState = digitalRead(BTN_PIN);
    if (pinState == LOW) {
        this->buttonCounter++;
    }
}

int RadiationCounterPlugin::getCurrentDisplayPage() const
{
    return this->buttonCounter % this->getDisplayPageCount();
}

int RadiationCounterPlugin::getSamplingInterval() const
{
    return 1;
}

void RadiationCounterPlugin::loop()
{
    int clicks = this->clickCounter;
    this->clickCounter = 0;

    this->calculate(clicks);
    this->aggregateGraph();
}

// --- Calculator ---

void RadiationCounterPlugin::calculate(int clicks)
{
    this->calcBuffer.push_back(clicks);

    if ((int)this->calcBuffer.size() > CALCULATOR_BUFFER_SIZE) {
        this->calcBuffer.erase(this->calcBuffer.begin());
    }

    int totalClicks = 0;
    for (auto& v : this->calcBuffer) totalClicks += v;
    this->cpm = totalClicks;

    float tubeFactor = this->storage->getParameter(PARAM_TUBE_FACTOR, "120").toFloat();
    this->dose = this->cpm / tubeFactor;
}

// --- Graph aggregator ---

void RadiationCounterPlugin::aggregateGraph()
{
    this->spanPointer++;
    int spanSize = this->storage->getParameter(PARAM_GRAPH_RESOLUTION, "600").toInt();

    this->spanBuffer.push_back(this->dose);
    if ((int)this->spanBuffer.size() > spanSize) {
        this->spanBuffer.erase(this->spanBuffer.begin());
    }

    if (this->spanPointer < spanSize) return;
    this->spanPointer = 0;

    // Calculate span average and add to graph buffer
    float sum = 0.0;
    for (auto& v : this->spanBuffer) sum += v;
    float spanDose = sum / this->spanBuffer.size();

    this->graphBuffer.push_back(spanDose);
    if ((int)this->graphBuffer.size() > GRAPH_BUFFER_SIZE) {
        this->graphBuffer.erase(this->graphBuffer.begin());
    }
}

// --- Parameters ---

void RadiationCounterPlugin::getParameterDefs(std::vector<ParameterDef>& defs) const
{
    defs.push_back({PARAM_TUBE_FACTOR, "Tube Factor (CPM/uSv/h)", "120", ParameterDef::NUMBER, false});
    defs.push_back({PARAM_GRAPH_RESOLUTION, "Graph Bar Seconds", "600", ParameterDef::NUMBER, false});
}

std::vector<const char*> RadiationCounterPlugin::getRequiredParameters() const
{
    return {};
}

// --- Stats ---

void RadiationCounterPlugin::getStats(std::vector<StatEntry>& entries) const
{
    entries.push_back({"CPM", String(this->cpm), (float)this->cpm, StatEntry::TEXT, true});
    entries.push_back({"Dose", String(this->dose, 2) + " \xC2\xB5Sv/h", this->dose, StatEntry::TEXT, true});
}

// --- MQTT ---

void RadiationCounterPlugin::publishMqtt(MQTTClient& client, const String& baseTopic)
{
    JsonDocument doc;
    String json;

    doc["cpm"] = this->cpm;
    doc["dose"] = this->dose;
    serializeJson(doc, json);

    client.publish(baseTopic.c_str(), json.c_str(), false, 0);
}

void RadiationCounterPlugin::publishHomeAssistantAutoconfig(MQTTClient& client, const String& deviceId, const String& stateTopic)
{
    // CPM sensor
    {
        JsonDocument doc;
        doc["name"] = "CPM sensor";
        doc["state_topic"] = stateTopic;
        doc["value_template"] = "{{ value_json.cpm | int }}";
        doc["unit_of_measurement"] = "CPM";
        doc["unique_id"] = deviceId + "_cpm_sensor";

        JsonObject device = doc["device"].to<JsonObject>();
        device["name"] = "ESP Radiation Counter";
        device["identifiers"][0] = deviceId;
        device["manufacturer"] = "VB";
        device["model"] = "ESP radiation counter v1";

        String json;
        serializeJson(doc, json);
        client.publish(("homeassistant/sensor/" + deviceId + "_cpm_sensor/config").c_str(), json.c_str(), true, 1);
    }

    // Dose sensor
    {
        JsonDocument doc;
        doc["name"] = "Dose sensor";
        doc["state_topic"] = stateTopic;
        doc["value_template"] = "{{ (value_json.dose | float) | round(2) }}";
        doc["unit_of_measurement"] = "\xC2\xB5Sv/h";
        doc["unique_id"] = deviceId + "_dose_sensor";

        JsonObject device = doc["device"].to<JsonObject>();
        device["name"] = "ESP Radiation Counter";
        device["identifiers"][0] = deviceId;
        device["manufacturer"] = "VB";
        device["model"] = "ESP radiation counter v1";

        String json;
        serializeJson(doc, json);
        client.publish(("homeassistant/sensor/" + deviceId + "_dose_sensor/config").c_str(), json.c_str(), true, 1);
    }
}

// --- Display ---

int RadiationCounterPlugin::getDisplayPageCount() const { return 2; }

int RadiationCounterPlugin::renderDisplayPage(U8G2& u8g2, int page, int width, int height) const
{
    if (page == 0) {
        this->renderGraphPage(u8g2, width, height);
        return height;
    }
    return 0;
}

void RadiationCounterPlugin::renderGraphPage(U8G2& u8g2, int width, int height) const
{
    int headerHeight = 16;

    // Header: CPM and dose
    u8g2.setDrawColor(1);
    u8g2.setFontMode(1);
    u8g2.setFont(u8g2_font_6x12_mf);

    int ascent = u8g2.getAscent();
    int descent = u8g2.getDescent();
    int headerMiddleY = headerHeight / 2 + ascent / 2 - descent / 2;

    String cpmStr = String(this->cpm) + " CPM";
    u8g2.drawStr(1, headerMiddleY, cpmStr.c_str());

    String doseStr = String(this->dose, 2) + " \xC2\xB5Sv/h";
    int doseW = u8g2.getUTF8Width(doseStr.c_str());
    u8g2.drawUTF8(width - doseW - 1, headerMiddleY, doseStr.c_str());

    // Graph area
    float max = 0.0;
    float min = 1.0;
    for (auto& v : this->graphBuffer) {
        if (v > max) max = v;
        if (v < min) min = v;
    }

    int chartY = headerHeight;
    int chartHeight = height - headerHeight;

    float yMin = min / 2.0;
    float yRange = max - yMin;
    if (yRange == 0) yRange = 1;

    int xStart = width - (int)this->graphBuffer.size();
    if (xStart < 0) xStart = 0;

    for (int i = 0; i < (int)this->graphBuffer.size(); i++) {
        float scaled = (this->graphBuffer[i] - yMin) / yRange;
        if (scaled < 0) scaled = 0;
        if (scaled > 1) scaled = 1;

        int pixelH = (int)(scaled * chartHeight);
        int xPos = xStart + i;
        if (xPos >= width) break;

        u8g2.drawVLine(xPos, chartY + chartHeight - pixelH, pixelH);
    }

    // Dotted header separator
    for (int i = 0; i < width; i++) {
        if (i % 4 == 0) u8g2.drawPixel(i, headerHeight);
    }

    // Y-axis labels
    u8g2.setFont(u8g2_font_5x7_tr);
    u8g2.setDrawColor(0);

    char maxText[10];
    dtostrf(max, 4, 2, maxText);
    char minText[10];
    dtostrf(min, 4, 2, minText);

    int maxTextWidth = u8g2.getStrWidth(maxText);
    int textY = headerHeight + u8g2.getAscent() + 3;
    int boxH = u8g2.getAscent() + 2;

    u8g2.drawBox(0, headerHeight + 1, maxTextWidth + 2, boxH * 2 + 4);
    u8g2.setDrawColor(1);
    u8g2.drawStr(0, textY, maxText);
    u8g2.drawStr(0, textY + boxH + 2, minText);

    // X-axis time label
    int spanSize = this->storage->getParameter(PARAM_GRAPH_RESOLUTION, "600").toInt();
    float maxSpanSec = (float)(spanSize * width);
    String duration;
    float span;
    if ((maxSpanSec / 60) < 60) {
        duration = "min";
        span = maxSpanSec / 60;
    } else if ((maxSpanSec / 3600) < 24) {
        duration = "h";
        span = maxSpanSec / 3600;
    } else {
        duration = "d";
        span = maxSpanSec / 86400;
    }

    u8g2.setDrawColor(2);
    String textZero = "-0" + duration;
    int textZeroWidth = u8g2.getStrWidth(textZero.c_str());
    u8g2.drawStr(width - textZeroWidth - 1, height - abs(u8g2.getDescent()), textZero.c_str());

    String textFull = "-" + String(span, 0) + duration;
    u8g2.drawStr(1, height - abs(u8g2.getDescent()), textFull.c_str());
}

