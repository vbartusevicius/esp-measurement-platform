#include "RadiationCounterPlugin.h"
#include <U8g2lib.h>
#include "HAL.h"
#include "LedController.h"
#include "Logger.h"
#include "Storage.h"

RadiationCounterPlugin* RadiationCounterPlugin::instance = nullptr;

// Common GM tubes: CPM per uSv/h and dead time. Published factors spread by
// +-20 % between batches and sources (Co-60 vs Cs-137 calibration), so these
// are the most widely used community values; calibrate against a reference
// instrument when accuracy matters. Dead time "0" = not published, correction off.
//   J305:    0.00812 uSv/h per CPM, 180 us (IoT-devices GGreg20_V3 notes)
//   M4011:   0.0065 uSv/h per CPM (DIYGeiger; radmon.org)
//   SBM-20 / STS-5: 0.0057 uSv/h per CPM (RH Geiger list), 190 us (datasheet)
//   SI-29BG: 122 CPM per uSv/h, batch dependent (DIYGeiger)
//   SBM-19:  0.0021 uSv/h per CPM (RH Geiger list)
//   LND 712: 108 CPM per uSv/h (DIYGeiger), 90 us (LND datasheet)
//   SI-3BG:  0.631578 uSv/h per CPM (radmon.org list), high-range tube
struct TubeModel {
    const char* id;
    const char* label;
    const char* factor;
    const char* deadTimeUs;
};

static const TubeModel TUBES[] = {
    {"j305", "J305 (glass, 107 mm)", "123.1", "180"},
    {"m4011", "M4011 (glass, 88 mm)", "153.8", "0"},
    {"sbm20", "SBM-20 / СБМ-20", "175.4", "190"},
    {"sts5", "STS-5 / СТС-5", "175.4", "190"},
    {"si29bg", "SI-29BG / СИ-29БГ", "122", "0"},
    {"sbm19", "SBM-19 / СБМ-19", "476.2", "0"},
    {"lnd712", "LND 712 (end window)", "108", "90"},
    {"si3bg", "SI-3BG / СИ-3БГ (high range)", "1.58", "0"},
};

IRAM_ATTR void RadiationCounterPlugin::radiationISR()
{
    if (instance) instance->onRadiationClick();
}

IRAM_ATTR void RadiationCounterPlugin::buttonISR()
{
    if (instance) instance->onButtonClick();
}

const char* RadiationCounterPlugin::getId() const { return "radiation_counter"; }
const char* RadiationCounterPlugin::getName() const { return "Radiation Counter Gateway"; }

void RadiationCounterPlugin::setup(HAL* hal, Storage* storage, Logger* logger, LedController* led)
{
    this->hal = hal;
    this->storage = storage;
    this->logger = logger;
    this->led = led;

    this->clickCounter = 0;
    this->buttonCounter = 0;
    this->radCalc.reset();

    this->tubeFactor = this->storage->getParameter(PARAM_TUBE_FACTOR, "123.1").toFloat();
    this->graphSpanSeconds = this->storage->getParameter(PARAM_GRAPH_RESOLUTION, "600").toInt();
    this->deadTimeUs = this->storage->getParameter(PARAM_DEAD_TIME_US, "180").toFloat();
    this->alertThresholdUsvH = this->storage->getParameter(PARAM_ALERT_THRESHOLD, "0.3").toFloat();
    this->totalCounts = 0;
    this->startedAt = this->hal->millis();
    this->lastPulseAt = 0;
    this->pulseSeen = false;
    this->lastClicks = 0;
    this->doseTrend.reset();
    this->doseExtremes.reset();

    this->hal->pinMode(CNT_PIN, INPUT);

    instance = this;
    this->hal->attachInterrupt(this->hal->pinToInterrupt(CNT_PIN), radiationISR, RISING);
    if (BTN_PIN >= 0) {
        this->hal->pinMode(BTN_PIN, INPUT);
        this->hal->attachInterrupt(this->hal->pinToInterrupt(BTN_PIN), buttonISR, FALLING);
    }
    logger->info("Radiation counter interrupts attached");
}

void RadiationCounterPlugin::onRadiationClick()
{
    this->clickCounter++;
    if (this->led) this->led->click();
}

void RadiationCounterPlugin::onButtonClick()
{
    this->buttonCounter++;
}

void RadiationCounterPlugin::nextDisplayPage()
{
    this->buttonCounter++;
}

int RadiationCounterPlugin::getCurrentDisplayPage() const
{
    return this->buttonCounter % this->getDisplayPageCount();
}

int RadiationCounterPlugin::getSamplingInterval() const
{
    return 1;
}

int RadiationCounterPlugin::getPublishInterval() const
{
    return 15;
}

void RadiationCounterPlugin::loop()
{
    // Swap the ISR-filled counter under a critical section so no pulses are lost
    noInterrupts();
    int clicks = this->clickCounter;
    this->clickCounter = 0;
    interrupts();

    unsigned long now = this->hal->millis();
    this->totalCounts += (unsigned long)clicks;
    this->lastClicks = clicks;
    if (clicks > 0) {
        this->lastPulseAt = now;
        this->pulseSeen = true;
    }
    this->radCalc.calculate(clicks, this->tubeFactor, this->deadTimeUs);
    this->radCalc.aggregateGraph(this->graphSpanSeconds);
    if (this->warmedUp()) {
        this->doseTrend.add(this->radCalc.getDose(), now);
        this->doseExtremes.update(this->radCalc.getDose(), now);
    }
}

// --- Parameters ---

void RadiationCounterPlugin::getParameterDefs(std::vector<ParameterDef>& defs) const
{
    defs.push_back({PARAM_TUBE_MODEL, "Geiger tube", "j305", ParameterDef::SELECT, false});
    defs.push_back({PARAM_TUBE_FACTOR, "Tube Factor (CPM/uSv/h)", "123.1", ParameterDef::NUMBER, false});
    defs.push_back({PARAM_DEAD_TIME_US, "Tube Dead Time (us, 0=off)", "180", ParameterDef::NUMBER, false});
    defs.push_back({PARAM_ALERT_THRESHOLD, "Alert Threshold (uSv/h avg)", "0.3", ParameterDef::NUMBER, false});
    defs.push_back({PARAM_GRAPH_RESOLUTION, "Graph Bar Seconds", "600", ParameterDef::NUMBER, false});
}

void RadiationCounterPlugin::getParameterChoices(std::vector<ParameterChoice>& choices) const
{
    for (const TubeModel& tube : TUBES) {
        choices.push_back({PARAM_TUBE_MODEL, tube.id, tube.label,
                           {{PARAM_TUBE_FACTOR, tube.factor}, {PARAM_DEAD_TIME_US, tube.deadTimeUs}}});
    }
    choices.push_back({PARAM_TUBE_MODEL, "custom", "Other / custom", {}});
}

// --- Stats ---

void RadiationCounterPlugin::getStats(std::vector<StatEntry>& entries) const
{
    int cpm = this->radCalc.getCPM();
    float dose = this->radCalc.getDose();
    float avg = this->radCalc.getDoseAvg5m();
    entries.push_back({"cpm", "CPM", String(cpm), (float)cpm});
    entries.push_back({"dose", "Dose", String(dose, 2) + " \xC2\xB5Sv/h", dose});
    entries.push_back({"dose_avg_5m", "Dose 5m avg", String(avg, 2) + " \xC2\xB5Sv/h", avg});
    if (avg >= this->alertThresholdUsvH) {
        entries.push_back({"alert", "Alert", "ELEVATED", 1.0f});
    }
    entries.push_back({"alert_threshold", "Alert Threshold", String(this->alertThresholdUsvH, 2) + " \xC2\xB5Sv/h", this->alertThresholdUsvH});
    entries.push_back({"counts_total", "Total Counts", String(this->totalCounts), (float)this->totalCounts});
}

// --- Screen model (OLED + WebUI) ---

bool RadiationCounterPlugin::warmedUp() const
{
    return this->hal->millis() - this->startedAt >= WARMUP_MS;
}

bool RadiationCounterPlugin::tubeOk() const
{
    // Background gives ~10-30 CPM on a J305, so 5 silent minutes means a dead
    // tube, missing HV or a broken pulse line.
    const unsigned long now = this->hal->millis();
    if (this->pulseSeen) return now - this->lastPulseAt < TUBE_SILENT_MS;
    return now - this->startedAt < TUBE_SILENT_MS;
}

bool RadiationCounterPlugin::getScreen(ScreenModel& model) const
{
    model.kind = "radiation";
    model.title = "RAD";
    model.value = this->radCalc.getDose();
    model.unit = "uSv/h";
    model.decimals = 2;
    model.valid = this->warmedUp() && this->tubeOk();
    model.scaleMin = 0.0f;
    model.trend = this->doseTrend.values();
    model.trendBucketSec = this->doseTrend.getBucketMs() / 1000UL;
    model.sensorLabel = "TUBE";
    model.sensorOk = this->tubeOk();
    model.raw = String(this->lastClicks) + "cps";
    model.signal = this->totalCounts >= 10000 ? String(this->totalCounts / 1000.0f, 1) + "kp" : String(this->totalCounts) + "p";
    if (this->doseExtremes.valid()) {
        model.low24 = this->doseExtremes.min();
        model.high24 = this->doseExtremes.max();
    }
    model.lines.push_back({"CPM", String(this->radCalc.getCPM())});
    model.lines.push_back({"5M", String(this->radCalc.getDoseAvg5m(), 2)});
    return true;
}

// --- MQTT ---

void RadiationCounterPlugin::publishMqtt(MQTTClient& client, const String& baseTopic)
{
    JsonDocument doc;
    doc["cpm"] = this->radCalc.getCPM();
    doc["dose"] = this->radCalc.getDose();
    doc["dose_avg_5m"] = this->radCalc.getDoseAvg5m();
    doc["counts_total"] = this->totalCounts;
    doc["alert"] = this->radCalc.getDoseAvg5m() >= this->alertThresholdUsvH;
    HaDiscovery::publishJson(client, baseTopic, doc);
}

void RadiationCounterPlugin::publishHomeAssistantAutoconfig(MQTTClient& client, const HaDiscoveryContext& ctx)
{
    static const HaEntity entities[] = {
        {"sensor", "cpm", "cpm", "CPM", "{{ value_json.cpm | int }}", "CPM", nullptr, "mdi:counter", true, false},
        {"sensor", "dose", "dose", "Dose Rate", "{{ (value_json.dose | float) | round(2) }}", "\xC2\xB5Sv/h", nullptr, "mdi:radioactive", true, false},
        {"sensor", "dose_avg", "dose_avg", "Dose Rate 5m Average", "{{ (value_json.dose_avg_5m | float) | round(2) }}", "\xC2\xB5Sv/h", nullptr, "mdi:radioactive", true, false},
        {"binary_sensor", "alert", "radiation_alert", "Elevated Radiation", "{{ 'ON' if value_json.alert else 'OFF' }}", nullptr, nullptr, "mdi:alert", false, false},
    };
    for (const HaEntity& entity : entities) HaDiscovery::publish(client, ctx, entity, ctx.nameOr("ESP Radiation Counter"));
}

bool RadiationCounterPlugin::getChartData(std::vector<float>& points, int& spanSeconds) const
{
    points = this->radCalc.getGraphData();
    spanSeconds = this->graphSpanSeconds;
    return true;
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

    String cpmStr = String(this->radCalc.getCPM()) + " CPM";
    u8g2.drawStr(1, headerMiddleY, cpmStr.c_str());

    String doseStr = String(this->radCalc.getDose(), 2) + " \xC2\xB5Sv/h";
    int doseW = u8g2.getUTF8Width(doseStr.c_str());
    u8g2.drawUTF8(width - doseW - 1, headerMiddleY, doseStr.c_str());

    // Graph area
    float max = 0.0;
    float min = 1.0;
    const auto& graphBuffer = this->radCalc.getGraphData();
    for (auto& v : graphBuffer) {
        if (v > max) max = v;
        if (v < min) min = v;
    }

    int chartY = headerHeight;
    int chartHeight = height - headerHeight;

    float yMin = min / 2.0;
    float yRange = max - yMin;
    if (yRange == 0) yRange = 1;

    int xStart = width - (int)graphBuffer.size();
    if (xStart < 0) xStart = 0;

    for (int i = 0; i < (int)graphBuffer.size(); i++) {
        float scaled = (graphBuffer[i] - yMin) / yRange;
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
    float maxSpanSec = (float)(this->graphSpanSeconds * width);
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

