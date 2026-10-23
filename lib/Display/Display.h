#ifndef DISPLAY_H
#define DISPLAY_H

#include <U8g2lib.h>
#include "DisplayFrame.h"
#include "IDisplayContributor.h"
#include "PortraitPages.h"

#if defined(BOARD_XIAO_ESP32C6)
// JLX12864OLED-S096W / QG-6428TSWCG02: SSD1312 128x64 at I2C 0x3C, mounted
// portrait (64x128) with the FPC tail at the top.
using BoardDisplay = U8G2_SSD1312_128X64_NONAME_F_HW_I2C;
#else
using BoardDisplay = U8G2_SSD1306_128X64_NONAME_F_HW_I2C;
#endif

// The board's OLED: owns the controller, the current page and the refresh.
// Portrait drawing is delegated to PortraitPages; landscape boards keep the
// plugin-drawn pages plus a system-info block.
class Display
{
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
        void nextPage() { this->page = (this->page + 1) % PortraitPages::PAGE_COUNT; }
        void configWizardFirstStep(const char* appName);

    private:
        void configWizard(const char* header, const char* helpLineOne, const char* helpLineTwo);
        void renderSystemInfo(int startY, bool mqttConnected);
};

#endif
