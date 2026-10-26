#include "PortraitPages.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include "DeviceMonitor.h"
#include <WiFi.h>

// Layout follows mechanical/scripts/oled_page1_bitmap.py (64x128 portrait).

static int wifiBars()
{
    if (WiFi.status() != WL_CONNECTED) return 0;
    int rssi = WiFi.RSSI();
    if (rssi >= -60) return 4;
    if (rssi >= -70) return 3;
    if (rssi >= -80) return 2;
    return rssi >= -90 ? 1 : 0;
}

PortraitPages::PortraitPages(U8G2& u8g2)
    : u8g2(u8g2), width(u8g2.getDisplayWidth()), height(u8g2.getDisplayHeight())
{
}

void PortraitPages::draw(const DisplayFrame& frame, int page)
{
    u8g2.setFontMode(1);
    u8g2.setDrawColor(1);
    const int alert = frame.monitor ? frame.monitor->pendingAlert() : -1;
    if (alert >= 0 && (size_t)alert < frame.screens.size()) {
        this->drawAlertModal(frame.screens[alert], frame.monitor->limits(alert), *frame.monitor);
        return;
    }
    const int sensorPages = pageCount(frame.screens.size()) - SYSTEM_PAGES;
    if (page < sensorPages) {
        if (frame.screens.empty()) this->drawNoSensorPage(frame);
        else this->drawSensorPage(frame, (size_t)page, page);
    } else if (page == sensorPages) {
        this->drawDevicePage(frame, page);
    } else if (page == sensorPages + 1) {
        this->drawLogPage(frame, page);
    } else {
        this->drawWifiPage(frame, page);
    }
}

void PortraitPages::drawText(int x, int top, const char* text)
{
    u8g2.setFont(u8g2_font_6x12_tr);
    u8g2.drawStr(x, top + 7, text);
}

void PortraitPages::drawRow(int top, const char* label, const String& value)
{
    u8g2.setFont(u8g2_font_6x12_tr);
    int labelEnd = 2 + u8g2.drawStr(2, top + 7, label);
    // Long values (e.g. 5-digit volumes) drop to the 4x6 font instead of running into the label
    if (62 - u8g2.getStrWidth(value.c_str()) < labelEnd + 4) u8g2.setFont(u8g2_font_4x6_tr);
    u8g2.drawStr(62 - u8g2.getStrWidth(value.c_str()), top + 7, value.c_str());
}

String PortraitPages::withUnit(const ScreenModel& screen, float value) const
{
    String text = screen.format(value);
    if (!std::isnan(value) && strlen(screen.unit) <= 3) text += screen.unit;
    return text;
}

void PortraitPages::drawHeader(const char* title, int page, int pages, bool mqtt)
{
    const int w = width;
    u8g2.setDrawColor(1);
    u8g2.drawBox(0, 0, w, 11);
    u8g2.setDrawColor(0);
    u8g2.setFont(u8g2_font_6x12_tr);
    u8g2.drawStr(2, 9, title);

    // WiFi bars, then an "M" while MQTT is connected, then the page number
    int bars = wifiBars();
    int bx = w - 34;
    for (int i = 0; i < 4; i++) {
        int bh = (i + 1) * 2;
        if (i < bars) u8g2.drawBox(bx + i * 3, 9 - bh, 2, bh);
        else u8g2.drawPixel(bx + i * 3, 8);
    }
    // "M" in the title font: in 4x6 an M is drawn like an H
    if (mqtt) {
        u8g2.setFont(u8g2_font_6x12_tr);
        u8g2.drawStr(w - 21, 9, "M");
    }
    u8g2.setFont(u8g2_font_4x6_tr);
    char number[8];
    snprintf(number, sizeof(number), "%d/%d", page + 1, pages);
    u8g2.drawStr(w - 1 - u8g2.getStrWidth(number), 8, number);
    u8g2.setDrawColor(1);
}

void PortraitPages::drawHero(const ScreenModel& screen, int top, int left, bool centred)
{
    String hero = screen.sensorOk ? screen.format(screen.value) : String("--");
    u8g2.setFont(u8g2_font_logisoso16_tn);
    int heroW = u8g2.getStrWidth(hero.c_str());

    // Long units stack in the small font; "L/min" and "uSv/h" as a fraction (L over min)
    const String unit = screen.unit;
    const bool stacked = unit.length() > 3;
    const int slash = unit.indexOf('/');
    const bool fraction = stacked && slash > 0;
    String unitTop = !stacked ? unit : fraction ? unit.substring(0, slash) : unit.substring(0, 3);
    String unitBottom = !stacked ? String() : fraction ? unit.substring(slash + 1) : unit.substring(3);

    u8g2.setFont(stacked ? u8g2_font_4x6_tr : u8g2_font_6x12_tr);
    int unitW = std::max<int>(u8g2.getStrWidth(unitTop.c_str()), stacked ? u8g2.getStrWidth(unitBottom.c_str()) : 0);
    int x = centred ? (width - heroW - 2 - unitW) / 2 : left;
    if (x < 0) x = 0;

    u8g2.setFont(u8g2_font_logisoso16_tn);
    u8g2.drawStr(x, top + 16, hero.c_str());
    if (stacked) {
        const int ux = x + heroW + 2;
        u8g2.setFont(u8g2_font_4x6_tr);
        if (fraction) {
            u8g2.drawStr(ux + (unitW - u8g2.getStrWidth(unitTop.c_str())) / 2, top + 6, unitTop.c_str());
            u8g2.drawHLine(ux, top + 8, unitW);
            u8g2.drawStr(ux + (unitW - u8g2.getStrWidth(unitBottom.c_str())) / 2, top + 15, unitBottom.c_str());
        } else {
            u8g2.drawStr(ux, top + 6, unitTop.c_str());
            u8g2.drawStr(ux, top + 14, unitBottom.c_str());
        }
    } else {
        u8g2.setFont(u8g2_font_6x12_tr);
        u8g2.drawStr(x + heroW + 2, top + 16, unitTop.c_str());
    }
}

void PortraitPages::axisRange(const ScreenModel& screen, const LimitMonitor* limits, float& lo, float& hi) const
{
    float dataLo = NAN, dataHi = NAN;
    auto take = [&](float v) {
        if (std::isnan(v)) return;
        if (std::isnan(dataLo) || v < dataLo) dataLo = v;
        if (std::isnan(dataHi) || v > dataHi) dataHi = v;
    };
    for (float v : screen.trend) take(v);
    take(screen.value);
    if (limits) {
        if (limits->hasLow()) take(limits->low());
        if (limits->hasHigh()) take(limits->high());
    }
    lo = std::isnan(screen.scaleMin) ? dataLo : screen.scaleMin;
    hi = std::isnan(screen.scaleMax) ? (std::isnan(dataHi) ? NAN : dataHi * 1.2f) : screen.scaleMax;
    if (std::isnan(lo)) lo = 0.0f;
    if (std::isnan(hi) || hi - lo < 1e-6f) hi = lo + 1.0f;
}

void PortraitPages::drawSparkline(const ScreenModel& screen, const LimitMonitor* limitsIn, int top, int boxHeight)
{
    u8g2.drawFrame(2, top, 60, boxHeight);
    const int bottom = top + boxHeight - 2;
    const int maxBar = boxHeight - 3;
    float lo, hi;
    this->axisRange(screen, limitsIn, lo, hi);

    int n = (int)screen.trend.size();
    if (n > 56) n = 56;
    int first = (int)screen.trend.size() - n;
    for (int i = 0; i < n; i++) {
        float ratio = (screen.trend[first + i] - lo) / (hi - lo);
        int bh = (int)lroundf(ratio * maxBar);
        if (bh < 1) bh = 1;
        if (bh > maxBar) bh = maxBar;
        u8g2.drawVLine(4 + (56 - n) + i, bottom - bh + 1, bh);
    }

    if (!limitsIn) return;
    // Dotted MIN/MAX lines in XOR so they stay visible over solid bars,
    // plus ticks outside the frame.
    const LimitMonitor& limits = *limitsIn;
    for (int k = 0; k < 2; k++) {
        bool has = k == 0 ? limits.hasLow() : limits.hasHigh();
        if (!has) continue;
        float ratio = ((k == 0 ? limits.low() : limits.high()) - lo) / (hi - lo);
        int y = bottom - (int)lroundf(ratio * maxBar);
        if (y <= top + 1 || y >= top + boxHeight - 1) continue;
        u8g2.drawPixel(0, y);
        u8g2.drawPixel(1, y);
        u8g2.drawPixel(62, y);
        u8g2.drawPixel(63, y);
        u8g2.setDrawColor(2);
        for (int x = 4; x < 60; x++) {
            if ((x - 4) % 3 != 2) u8g2.drawPixel(x, y);
        }
        u8g2.setDrawColor(1);
    }
}

void PortraitPages::drawPill(int x, int y, const char* label, bool ok)
{
    u8g2.setFont(u8g2_font_4x6_tr);
    u8g2.drawStr(x, y + 6, label);
    int bx = x + u8g2.getStrWidth(label) + 2;
    u8g2.drawFrame(bx, y, 7, 7);
    if (ok) {
        for (int d = 1; d < 6; d++) {
            u8g2.drawPixel(bx + d, y + d);
            u8g2.drawPixel(bx + 6 - d, y + d);
        }
    }
}

void PortraitPages::drawIpFooter()
{
    u8g2.drawFrame(0, 101, width, 27);
    if (WiFi.status() != WL_CONNECTED) {
        this->drawText(3, 110, "NO WIFI");
        return;
    }
    String ip = WiFi.localIP().toString();
    int dot = ip.indexOf('.', ip.indexOf('.') + 1);
    this->drawText(3, 105, dot > 0 ? ip.substring(0, dot + 1).c_str() : ip.c_str());
    if (dot > 0) this->drawText(3, 116, ip.substring(dot + 1, ip.length()).c_str());
}

void PortraitPages::drawNoSensorPage(const DisplayFrame& frame)
{
    this->drawHeader("SETUP", 0, pageCount(0), frame.mqttConnected);
    this->drawText(2, 20, "NO SENSOR");
    this->drawText(2, 34, "OPEN THE");
    this->drawText(2, 45, "WEB UI AT:");
    this->drawIpFooter();
}

// One sensor: its reading, trend and two secondary lines, then its own
// diagnostics (sensor state + terminal signal, then two rows: 24 h low / high
// unless the plugin supplies better ones in ScreenModel::details).
void PortraitPages::drawSensorPage(const DisplayFrame& frame, size_t sensor, int page)
{
    const ScreenModel& screen = frame.screens[sensor];
    const LimitMonitor* limits = frame.monitor && sensor < frame.monitor->sensorCount() ? &frame.monitor->limits(sensor) : nullptr;
    this->drawHeader(screen.title, page, pageCount(frame.screens.size()), frame.mqttConnected);

    this->drawHero(screen, 14, 2, true);
    this->drawSparkline(screen, limits, 32, 27);
    for (size_t i = 0; i < screen.lines.size() && i < 2; i++) {
        this->drawRow(63 + (int)i * 10, screen.lines[i].label, screen.lines[i].value);
    }
    u8g2.drawHLine(0, 83, width);
    this->drawPill(2, 87, screen.sensorLabel, screen.sensorOk);
    u8g2.setFont(u8g2_font_4x6_tr);
    const String signal = screen.signal.isEmpty() ? String("--") : screen.signal;
    u8g2.drawStr(62 - u8g2.getStrWidth(signal.c_str()), 93, signal.c_str());
    if (screen.details.empty()) {
        this->drawRow(100, "24L", this->withUnit(screen, screen.low24));
        this->drawRow(112, "24H", this->withUnit(screen, screen.high24));
    } else {
        for (size_t i = 0; i < screen.details.size() && i < 2; i++) {
            this->drawRow(100 + (int)i * 12, screen.details[i].label, screen.details[i].value);
        }
    }
}

// Device-wide state, shown once instead of on every sensor page.
void PortraitPages::drawDevicePage(const DisplayFrame& frame, int page)
{
    this->drawHeader("DEV", page, pageCount(frame.screens.size()), frame.mqttConnected);
    this->drawRow(14, "MQTT", frame.mqttConnected ? String("ON") : String("OFF"));
    this->drawRow(24, "WIFI", WiFi.status() == WL_CONNECTED ? String(WiFi.RSSI()) : String("OFF"));
    u8g2.drawHLine(0, 35, width);

    String relay = "N/A";
    String follows = "";
    if (frame.monitor && frame.monitor->relayAvailable()) {
        relay = String(frame.monitor->relayOn() ? "ON" : "OFF") + "(" + String(frame.monitor->relayActivations()) + ")";
        const int source = frame.monitor->relaySource();
        follows = source >= 0 && (size_t)source < frame.screens.size() ? String(frame.screens[source].title) : String("MANUAL");
    }
    this->drawRow(38, "RLY", relay);
    if (follows.length()) this->drawRow(48, "BY", follows);
    this->drawRow(58, "HEAP", String((unsigned long)(ESP.getFreeHeap() / 1024)) + "KB");
    this->drawRow(68, "ERRS", String(frame.errors));

    unsigned long secs = millis() / 1000UL;
    unsigned long days = secs / 86400UL, hours = (secs / 3600UL) % 24UL, minutes = (secs / 60UL) % 60UL;
    char up[16];
    if (days > 0) snprintf(up, sizeof(up), "UP %lud %02luh", days, hours);
    else snprintf(up, sizeof(up), "UP %02luh %02lum", hours, minutes);
    this->drawText(2, 80, up);
    this->drawIpFooter();
}

void PortraitPages::drawLogPage(const DisplayFrame& frame, int page)
{
    this->drawHeader("LOG", page, pageCount(frame.screens.size()), frame.mqttConnected);
    if (!frame.monitor || frame.monitor->events().size() == 0) {
        this->drawText(2, 20, "NO EVENTS");
        return;
    }
    const EventLog& events = frame.monitor->events();
    u8g2.setFont(u8g2_font_4x6_tr);
    int y = 13;
    for (size_t i = 0; i < events.size() && y + 11 <= 127; i++) {
        const EventLog::Entry& entry = events.newest(i);
        u8g2.drawStr(2, y + 5, entry.title);
        u8g2.drawStr(2, y + 11, entry.detail);
        y += 12;
        if (i + 1 < events.size() && y < 126) {
            u8g2.drawHLine(0, y, width);
            y += 2;
        }
    }
}

void PortraitPages::drawWifiPage(const DisplayFrame& frame, int page)
{
    this->drawHeader("WIFI", page, pageCount(frame.screens.size()), frame.mqttConnected);
    this->drawText(2, 16, "STATE:");
    if (WiFi.status() == WL_CONNECTED) {
        this->drawRow(27, "ONLINE", String(WiFi.RSSI()));
    } else {
        this->drawText(2, 27, "NO SIGNAL");
    }
    u8g2.drawHLine(0, 39, width);
    this->drawText(2, 45, "TO CONFIG");
    this->drawText(2, 56, "WIFI AP:");

    u8g2.drawBox(2, 70, 60, 28);
    u8g2.setDrawColor(0);
    this->drawText(5, 74, "HOLD RST");
    this->drawText(5, 86, "FOR 5 SEC");
    u8g2.setDrawColor(1);

    u8g2.setFont(u8g2_font_4x6_tr);
    u8g2.drawStr(3, 110, "DEVICE REBOOTS");
    u8g2.drawStr(3, 119, "INTO SETUP AP");
}

void PortraitPages::drawGauge(const ScreenModel& screen, const LimitMonitor& limits, int top, int boxHeight)
{
    float lo, hi;
    this->axisRange(screen, &limits, lo, hi);
    auto toX = [&](float v) {
        float ratio = (v - lo) / (hi - lo);
        if (ratio < 0.0f) ratio = 0.0f;
        if (ratio > 1.0f) ratio = 1.0f;
        return 4 + (int)lroundf(56 * ratio);
    };
    u8g2.drawFrame(2, top, 60, boxHeight);
    int fill = toX(screen.value) - 4;
    if (fill > 0) u8g2.drawBox(4, top + 2, fill, boxHeight - 4);
    for (int pct = 25; pct <= 75; pct += 25) u8g2.drawPixel(4 + 56 * pct / 100, top + boxHeight);
    if (limits.hasLow()) u8g2.drawVLine(toX(limits.low()), top - 1, boxHeight + 2);
    if (limits.hasHigh()) u8g2.drawVLine(toX(limits.high()), top - 1, boxHeight + 2);
}

void PortraitPages::drawAlertModal(const ScreenModel& screen, const LimitMonitor& limits, const DeviceMonitor& monitor)
{
    const bool below = limits.state() == LimitMonitor::State::BELOW;
    u8g2.drawFrame(0, 0, width, height);
    u8g2.drawBox(1, 1, 62, 14);
    u8g2.setDrawColor(0);
    const String banner = String("! ") + screen.title + " !";   // which sensor
    this->drawText((width - 6 * (int)banner.length()) / 2, 4, banner.c_str());
    u8g2.setDrawColor(1);

    String hero = screen.format(screen.value);
    u8g2.setFont(u8g2_font_logisoso16_tn);
    int heroW = u8g2.getStrWidth(hero.c_str());
    u8g2.drawStr(4, 21 + 16, hero.c_str());
    u8g2.setFont(u8g2_font_4x6_tr);
    u8g2.drawStr(4 + heroW + 2, 22 + 6, below ? "MIN" : "MAX");
    u8g2.drawStr(4 + heroW + 2, 30 + 6, "HIT");

    this->drawGauge(screen, limits, 42, 13);

    String limit = String("LIM ") + (below ? "<" : ">") + this->withUnit(screen, limits.activeLimit());
    this->drawText(4, 62, limit.c_str());

    u8g2.drawBox(2, 76, 60, 17);
    u8g2.setDrawColor(0);
    String relay = monitor.relayAvailable() ? String("RELAY ") + (monitor.relayOn() ? " ON" : "OFF") : String("NO RELAY");
    this->drawText(5, 81, relay.c_str());
    u8g2.setDrawColor(1);

    u8g2.drawHLine(2, 101, 60);
    this->drawText(3, 106, "TAP PAGE:");
    this->drawText(3, 116, "DISMISS");
}

void PortraitPages::drawPortalModal(const char* apName, const char* portalIp)
{
    u8g2.drawFrame(0, 0, width, height);
    u8g2.drawBox(1, 1, 62, 12);
    u8g2.setDrawColor(0);
    this->drawText(4, 3, "WIFI SETUP");
    u8g2.setDrawColor(1);

    this->drawText(3, 17, "1.JOIN AP:");
    u8g2.drawBox(2, 27, 60, 23);
    u8g2.setDrawColor(0);
    String name = apName;
    this->drawText(4, 30, name.substring(0, 9).c_str());
    if (name.length() > 9) this->drawText(4, 40, name.substring(9, 18).c_str());
    u8g2.setDrawColor(1);

    this->drawText(3, 55, "2.BROWSER:");
    u8g2.drawFrame(2, 65, 60, 23);
    String ip = portalIp;
    int dot = ip.indexOf('.', ip.indexOf('.') + 1);
    this->drawText(5, 68, dot > 0 ? ip.substring(0, dot + 1).c_str() : ip.c_str());
    if (dot > 0) this->drawText(5, 78, ip.substring(dot + 1, ip.length()).c_str());

    u8g2.drawHLine(2, 94, 60);
    this->drawText(3, 99, "AP ACTIVE");
    this->drawText(3, 109, "HOLD RST");
    this->drawText(3, 118, "5S: EXIT");
}
