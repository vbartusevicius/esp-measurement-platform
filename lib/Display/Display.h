#ifndef DISPLAY_H
#define DISPLAY_H

#include <Arduino.h>
#include <U8g2lib.h>
#include "IDisplayContributor.h"
#include "ScreenModel.h"

class DeviceMonitor;

#if defined(BOARD_XIAO_ESP32C6)
// JLX12864OLED-S096W / QG-6428TSWCG02: SSD1312 128x64 at I2C 0x3C, mounted
// portrait (64x128) with the FPC tail at the top.
using BoardDisplay = U8G2_SSD1312_128X64_NONAME_F_HW_I2C;
#else
using BoardDisplay = U8G2_SSD1306_128X64_NONAME_F_HW_I2C;
#endif

// Everything one display refresh needs. Portrait (64 px wide) boards render
// the page system from `screen` + `monitor`; landscape boards keep the
// plugin-drawn pages (`legacy`).
struct DisplayFrame {
    IDisplayContributor* legacy = nullptr;
    int legacyPage = 0;
    const ScreenModel* screen = nullptr;
    const DeviceMonitor* monitor = nullptr;
    bool mqttConnected = false;
    unsigned long errors = 0;
};

class Display
{
    public:
        static constexpr int PORTRAIT_PAGES = 4;   // main, STAT, LOG, WIFI

    private:
        BoardDisplay u8g2;
        int displayWidth = 128;
        int displayHeight = 64;
        int page = 0;

    public:
        Display();
        void begin();
        bool isPortrait() const { return this->displayWidth < 100; }
        void run(const DisplayFrame& frame);
        void nextPage() { this->page = (this->page + 1) % PORTRAIT_PAGES; }
        int getPage() const { return this->page; }
        void configWizardFirstStep(const char* appName);
        void configWizardSecondStep(const char* ipAddress);

    private:
        void configWizard(const char* header, const char* helpLineOne, const char* helpLineTwo);
        void renderSystemInfo(int startY, bool mqttConnected);

        // Portrait (64x128) page system, layout per mechanical/scripts/oled_page1_bitmap.py
        void renderPortrait(const DisplayFrame& frame);
        void drawHeader(const char* title, int pageNumber);
        void drawMainPage(const DisplayFrame& frame);
        void drawStatPage(const DisplayFrame& frame);
        void drawLogPage(const DisplayFrame& frame);
        void drawWifiPage();
        void drawAlertModal(const ScreenModel& screen, const DeviceMonitor& monitor);
        void drawPortalModal(const char* apName, const char* portalIp);
        void drawHero(const ScreenModel& screen, int top, int left, bool centred);
        void drawSparkline(const ScreenModel& screen, const DeviceMonitor* monitor, int top, int height);
        void drawGauge(const ScreenModel& screen, const DeviceMonitor& monitor, int top, int height);
        void drawPill(int x, int y, const char* label, bool ok);
        void drawText(int x, int top, const char* text);
        void drawRow(int top, const char* label, const String& value);
        void drawIpFooter();
        void axisRange(const ScreenModel& screen, const DeviceMonitor* monitor, float& lo, float& hi) const;
        String withUnit(const ScreenModel& screen, float value) const;
};

#endif
