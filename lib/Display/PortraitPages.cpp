#include "PortraitPages.h"
#include <cmath>
#include <cstdio>
#include <cstring>
#include "DeviceMonitor.h"
#include "PlatformWiFi.h"

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
    if (frame.screen && frame.monitor && frame.monitor->alertPending()) {
        this->drawAlertModal(*frame.screen, *frame.monitor);
        return;
    }
    switch (page) {
        case 1: this->drawStatPage(frame); break;
        case 2: this->drawLogPage(frame); break;
        case 3: this->drawWifiPage(); break;
        default: this->drawMainPage(frame); break;
    }
}

void PortraitPages::drawText(int x, int top, const char* text)
{
    u8g2.setFont(u8g2_font_6x10_tr);
    u8g2.drawStr(x, top + 7, text);
}

void PortraitPages::drawRow(int top, const char* label, const String& value)
{
    u8g2.setFont(u8g2_font_6x10_tr);
    int labelEnd = 2 + u8g2.drawStr(2, top + 7, label);
    // Long values (e.g. 5-digit volumes) drop to the 4x6 font instead of overwriting the label
    if (62 - u8g2.getStrWidth(value.c_str()) <= labelEnd) u8g2.setFont(u8g2_font_4x6_tr);
    u8g2.drawStr(62 - u8g2.getStrWidth(value.c_str()), top + 7, value.c_str());
}

String PortraitPages::withUnit(const ScreenModel& screen, float value) const
{
    String text = screen.format(value);
    if (!std::isnan(value) && strlen(screen.unit) <= 3) text += screen.unit;
    return text;
}

void PortraitPages::drawHeader(const char* title, int pageNumber)
{
    const int w = width;
    u8g2.setDrawColor(1);
    u8g2.drawBox(0, 0, w, 11);
    u8g2.setDrawColor(0);
    u8g2.setFont(u8g2_font_6x10_tr);
    u8g2.drawStr(2, 9, title);

    int bars = wifiBars();
    int bx = w - 28;
    for (int i = 0; i < 4; i++) {
        int bh = (i + 1) * 2;
        if (i < bars) u8g2.drawBox(bx + i * 3, 9 - bh, 2, bh);
        else u8g2.drawPixel(bx + i * 3, 8);
    }
    u8g2.drawVLine(w - 15, 1, 9);

    int px = w - 13;
    for (int p = 1; p <= PAGE_COUNT; p++) {
        if (p == pageNumber) {
            u8g2.drawBox(px, 3, 3, 5);
            px += 5;
        } else {
            u8g2.drawPixel(px, 5);
            px += 2;
        }
    }
    u8g2.setDrawColor(1);
}

void PortraitPages::drawHero(const ScreenModel& screen, int top, int left, bool centred)
{
    String hero = screen.sensorOk ? screen.format(screen.value) : String("--");
    u8g2.setFont(u8g2_font_logisoso16_tn);
    int heroW = u8g2.getStrWidth(hero.c_str());

    const char* unit = screen.unit;
    bool stacked = strlen(unit) > 3;
    String unitTop = stacked ? String(unit).substring(0, 3) : String(unit);
    String unitBottom = stacked ? String(unit).substring(3, strlen(unit)) : String();

    u8g2.setFont(stacked ? u8g2_font_4x6_tr : u8g2_font_6x10_tr);
    int unitW = u8g2.getStrWidth(unitTop.c_str());
    int x = centred ? (width - heroW - 2 - unitW) / 2 : left;
    if (x < 0) x = 0;

    u8g2.setFont(u8g2_font_logisoso16_tn);
    u8g2.drawStr(x, top + 16, hero.c_str());
    if (stacked) {
        u8g2.setFont(u8g2_font_4x6_tr);
        u8g2.drawStr(x + heroW + 2, top + 6, unitTop.c_str());
        u8g2.drawStr(x + heroW + 2, top + 14, unitBottom.c_str());
    } else {
        u8g2.setFont(u8g2_font_6x10_tr);
        u8g2.drawStr(x + heroW + 2, top + 16, unitTop.c_str());
    }
}

void PortraitPages::axisRange(const ScreenModel& screen, const DeviceMonitor* monitor, float& lo, float& hi) const
{
    float dataLo = NAN, dataHi = NAN;
    auto take = [&](float v) {
        if (std::isnan(v)) return;
        if (std::isnan(dataLo) || v < dataLo) dataLo = v;
        if (std::isnan(dataHi) || v > dataHi) dataHi = v;
    };
    for (float v : screen.trend) take(v);
    take(screen.value);
    if (monitor) {
        if (monitor->limits().hasLow()) take(monitor->limits().low());
        if (monitor->limits().hasHigh()) take(monitor->limits().high());
    }
    lo = std::isnan(screen.scaleMin) ? dataLo : screen.scaleMin;
    hi = std::isnan(screen.scaleMax) ? (std::isnan(dataHi) ? NAN : dataHi * 1.2f) : screen.scaleMax;
    if (std::isnan(lo)) lo = 0.0f;
    if (std::isnan(hi) || hi - lo < 1e-6f) hi = lo + 1.0f;
}

void PortraitPages::drawSparkline(const ScreenModel& screen, const DeviceMonitor* monitor, int top, int boxHeight)
{
    u8g2.drawFrame(2, top, 60, boxHeight);
    const int bottom = top + boxHeight - 2;
    const int maxBar = boxHeight - 3;
    float lo, hi;
    this->axisRange(screen, monitor, lo, hi);

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

    if (!monitor) return;
    // Dotted MIN/MAX lines in XOR so they stay visible over solid bars,
    // plus ticks outside the frame.
    const LimitMonitor& limits = monitor->limits();
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

void PortraitPages::drawMainPage(const DisplayFrame& frame)
{
    const ScreenModel* screen = frame.screen;
    this->drawHeader(screen ? screen->title : "SETUP", 1);

    if (!screen) {
        this->drawText(2, 20, "NO PLUGIN");
        this->drawText(2, 34, "OPEN THE");
        this->drawText(2, 45, "WEB UI AT:");
        this->drawIpFooter();
        return;
    }

    this->drawHero(*screen, 14, 2, true);
    this->drawSparkline(*screen, frame.monitor, 32, 27);
    for (size_t i = 0; i < screen->lines.size() && i < 2; i++) {
        this->drawRow(63 + (int)i * 10, screen->lines[i].label, screen->lines[i].value);
    }
    u8g2.drawHLine(0, 83, width);
    this->drawPill(2, 88, "MQTT", frame.mqttConnected);
    this->drawPill(34, 88, screen->sensorLabel, screen->sensorOk);
    this->drawIpFooter();
}

void PortraitPages::drawStatPage(const DisplayFrame& frame)
{
    this->drawHeader("STAT", 2);
    const ScreenModel* screen = frame.screen;

    this->drawRow(16, "RAW", screen && !screen->raw.isEmpty() ? screen->raw : String("--"));
    this->drawRow(28, "SIG", screen && !screen->signal.isEmpty() ? screen->signal : String("--"));
    u8g2.drawHLine(0, 39, width);

    this->drawRow(44, "24L:", screen ? this->withUnit(*screen, screen->low24) : String("--"));
    this->drawRow(56, "24H:", screen ? this->withUnit(*screen, screen->high24) : String("--"));
    u8g2.drawHLine(0, 67, width);

    String relay = "N/A";
    if (frame.monitor && frame.monitor->relayAvailable()) {
        relay = String(frame.monitor->relayOn() ? "ON" : "OFF") + "(" + String(frame.monitor->relayActivations()) + ")";
    }
    this->drawRow(72, "RLY:", relay);
    this->drawRow(84, "HEAP:", String((unsigned long)(ESP.getFreeHeap() / 1024)) + "KB");
    this->drawRow(96, "ERRS:", String(frame.errors));

    unsigned long secs = millis() / 1000UL;
    unsigned long days = secs / 86400UL, hours = (secs / 3600UL) % 24UL, minutes = (secs / 60UL) % 60UL;
    char up[16];
    if (days > 0) snprintf(up, sizeof(up), "UP %lud %02luh", days, hours);
    else snprintf(up, sizeof(up), "UP %02luh %02lum", hours, minutes);
    u8g2.drawBox(0, 111, width, 17);
    u8g2.setDrawColor(0);
    this->drawText(3, 116, up);
    u8g2.setDrawColor(1);
}

void PortraitPages::drawLogPage(const DisplayFrame& frame)
{
    this->drawHeader("LOG", 3);
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

void PortraitPages::drawWifiPage()
{
    this->drawHeader("WIFI", 4);
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

void PortraitPages::drawGauge(const ScreenModel& screen, const DeviceMonitor& monitor, int top, int boxHeight)
{
    float lo, hi;
    this->axisRange(screen, &monitor, lo, hi);
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
    if (monitor.limits().hasLow()) u8g2.drawVLine(toX(monitor.limits().low()), top - 1, boxHeight + 2);
    if (monitor.limits().hasHigh()) u8g2.drawVLine(toX(monitor.limits().high()), top - 1, boxHeight + 2);
}

void PortraitPages::drawAlertModal(const ScreenModel& screen, const DeviceMonitor& monitor)
{
    const bool below = monitor.limits().state() == LimitMonitor::State::BELOW;
    u8g2.drawFrame(0, 0, width, height);
    u8g2.drawBox(1, 1, 62, 14);
    u8g2.setDrawColor(0);
    this->drawText(5, 4, "! ALERT !");
    u8g2.setDrawColor(1);

    String hero = screen.format(screen.value);
    u8g2.setFont(u8g2_font_logisoso16_tn);
    int heroW = u8g2.getStrWidth(hero.c_str());
    u8g2.drawStr(4, 21 + 16, hero.c_str());
    u8g2.setFont(u8g2_font_4x6_tr);
    u8g2.drawStr(4 + heroW + 2, 22 + 6, below ? "MIN" : "MAX");
    u8g2.drawStr(4 + heroW + 2, 30 + 6, "HIT");

    this->drawGauge(screen, monitor, 42, 13);

    String limit = String("LIM:") + (below ? "<" : ">") + this->withUnit(screen, monitor.limits().activeLimit());
    this->drawText(4, 62, limit.c_str());

    u8g2.drawBox(2, 76, 60, 17);
    u8g2.setDrawColor(0);
    String relay = monitor.relayAvailable() ? String("RELAY:") + (monitor.relayOn() ? " ON" : "OFF") : String("NO RELAY");
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
