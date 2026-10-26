#ifndef PORTRAIT_PAGES_H
#define PORTRAIT_PAGES_H

#include <Arduino.h>
#include <U8g2lib.h>
#include "DisplayFrame.h"
#include "ScreenModel.h"

class DeviceMonitor;
class LimitMonitor;

// Draws the 64x128 portrait pages into the caller's buffer: one page per
// sensor (its reading and sensor diagnostics), then DEV (network, MQTT,
// relay, system), LOG and WIFI; plus the alert and WiFi-setup pop-ups. The
// header of every page shows the WiFi bars, an MQTT mark and the page number.
// Owns no state between frames.
class PortraitPages
{
    public:
        static constexpr int SYSTEM_PAGES = 3;
        static int pageCount(size_t sensors) { return (int)(sensors ? sensors : 1) + SYSTEM_PAGES; }

        explicit PortraitPages(U8G2& u8g2);
        void draw(const DisplayFrame& frame, int page);
        void drawPortalModal(const char* apName, const char* portalIp);

    private:
        U8G2& u8g2;
        const int width;
        const int height;

        void drawHeader(const char* title, int page, int pages, bool mqtt);
        void drawSensorPage(const DisplayFrame& frame, size_t sensor, int page);
        void drawNoSensorPage(const DisplayFrame& frame);
        void drawDevicePage(const DisplayFrame& frame, int page);
        void drawLogPage(const DisplayFrame& frame, int page);
        void drawWifiPage(const DisplayFrame& frame, int page);
        void drawAlertModal(const ScreenModel& screen, const LimitMonitor& limits, const DeviceMonitor& monitor);
        void drawHero(const ScreenModel& screen, int top, int left, bool centred);
        void drawSparkline(const ScreenModel& screen, const LimitMonitor* limits, int top, int boxHeight);
        void drawGauge(const ScreenModel& screen, const LimitMonitor& limits, int top, int boxHeight);
        void drawPill(int x, int y, const char* label, bool ok);
        void drawText(int x, int top, const char* text);
        void drawRow(int top, const char* label, const String& value);
        void drawIpFooter();
        void axisRange(const ScreenModel& screen, const LimitMonitor* limits, float& lo, float& hi) const;
        String withUnit(const ScreenModel& screen, float value) const;
};

#endif
