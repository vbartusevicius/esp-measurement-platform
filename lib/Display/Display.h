#ifndef DISPLAY_H
#define DISPLAY_H

#include <Arduino.h>
#include <U8g2lib.h>
#include "IDisplayContributor.h"

#if defined(BOARD_XIAO_ESP32C6)
// JLX12864OLED-S096W / QG-6428TSWCG02: SSD1312 128x64 at I2C 0x3C, mounted
// portrait (64x128) with the FPC tail at the top.
using BoardDisplay = U8G2_SSD1312_128X64_NONAME_F_HW_I2C;
#else
using BoardDisplay = U8G2_SSD1306_128X64_NONAME_F_HW_I2C;
#endif

class Display
{
    private:
        BoardDisplay u8g2;
        int displayWidth;
        int displayHeight;

    public:
        Display();
        void begin();
        void run(IDisplayContributor* plugin, int page, bool mqttConnected);
        void configWizardFirstStep(const char* appName);
        void configWizardSecondStep(const char* ipAddress);

    private:
        void configWizard(const char* header, const char* helpLineOne, const char* helpLineTwo);
        void renderSystemInfo(int startY, bool mqttConnected);
};

#endif
