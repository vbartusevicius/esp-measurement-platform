#include "Display.h"
#include "Board.h"
#include "PortraitPages.h"

// RES# has its own RC power-on reset on the UI board. If the first prototype
// shows the image upside down, set DISPLAY_ROTATION to 3 (U8G2_R3).
static constexpr int DISPLAY_ROTATION = 1;

Display::Display()
    : u8g2(DISPLAY_ROTATION == 3 ? U8G2_R3 : U8G2_R1, U8X8_PIN_NONE, Board::I2C_SCL_PIN, Board::I2C_SDA_PIN)
{
}

void Display::begin()
{
    u8g2.begin();
    u8g2.setContrast(0x7F);
}

void Display::run(const DisplayFrame& frame)
{
    u8g2.clearBuffer();
    PortraitPages(u8g2).draw(frame, this->page);
    u8g2.sendBuffer();
}

void Display::showSetupPortal(const char* apName)
{
    u8g2.clearBuffer();
    PortraitPages(u8g2).drawPortalModal(apName, "192.168.4.1");
    u8g2.sendBuffer();
}
