#ifndef PORTRAIT_PAGES_H
#define PORTRAIT_PAGES_H

#include <Arduino.h>
#include <U8g2lib.h>
#include "DisplayFrame.h"
#include "ScreenModel.h"

class DeviceMonitor;

// Draws the 64x128 portrait pages (main, STAT, LOG, WIFI) and the alert and
// WiFi-setup pop-ups into the caller's buffer. Owns no state between frames.
class PortraitPages
{
    public:
        static constexpr int PAGE_COUNT = 4;

        explicit PortraitPages(U8G2& u8g2);
        void draw(const DisplayFrame& frame, int page);
        void drawPortalModal(const char* apName, const char* portalIp);

    private:
        U8G2& u8g2;
        const int width;
        const int height;

        void drawHeader(const char* title, int pageNumber);
        void drawMainPage(const DisplayFrame& frame);
        void drawStatPage(const DisplayFrame& frame);
        void drawLogPage(const DisplayFrame& frame);
        void drawWifiPage();
        void drawAlertModal(const ScreenModel& screen, const DeviceMonitor& monitor);
        void drawHero(const ScreenModel& screen, int top, int left, bool centred);
        void drawSparkline(const ScreenModel& screen, const DeviceMonitor* monitor, int top, int boxHeight);
        void drawGauge(const ScreenModel& screen, const DeviceMonitor& monitor, int top, int boxHeight);
        void drawPill(int x, int y, const char* label, bool ok);
        void drawText(int x, int top, const char* text);
        void drawRow(int top, const char* label, const String& value);
        void drawIpFooter();
        void axisRange(const ScreenModel& screen, const DeviceMonitor* monitor, float& lo, float& hi) const;
        String withUnit(const ScreenModel& screen, float value) const;
};

#endif
