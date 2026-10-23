#ifndef DISPLAY_H
#define DISPLAY_H

#include <U8g2lib.h>
#include "DisplayFrame.h"
#include "PortraitPages.h"

// The UI board OLED (JLX12864OLED-S096W / QG-6428TSWCG02: SSD1312 128x64 at
// I2C 0x3C, mounted portrait 64x128 with the FPC tail at the top): owns the
// controller and the current page; PortraitPages does the drawing.
class Display
{
    private:
        U8G2_SSD1312_128X64_NONAME_F_HW_I2C u8g2;
        int page = 0;

    public:
        Display();
        void begin();
        void run(const DisplayFrame& frame);
        void nextPage() { this->page = (this->page + 1) % PortraitPages::PAGE_COUNT; }
        void showSetupPortal(const char* apName);
};

#endif
