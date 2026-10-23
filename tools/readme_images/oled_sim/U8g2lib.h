#pragma once
// Host simulator: the real U8g2 C core behind the small C++ API Display.cpp uses.
extern "C" {
#include "u8g2.h"
}
#define U8X8_PIN_NONE 255
#define U8G2_R0 (&u8g2_cb_r0)
#define U8G2_R1 (&u8g2_cb_r1)
#define U8G2_R2 (&u8g2_cb_r2)
#define U8G2_R3 (&u8g2_cb_r3)
class U8G2 {
public:
    u8g2_t u8g2;
    void begin() { u8g2_InitDisplay(&u8g2); u8g2_SetPowerSave(&u8g2, 0); u8g2_ClearBuffer(&u8g2); }
    void setContrast(uint8_t) {}
    int getDisplayWidth() { return u8g2_GetDisplayWidth(&u8g2); }
    int getDisplayHeight() { return u8g2_GetDisplayHeight(&u8g2); }
    void clearBuffer() { u8g2_ClearBuffer(&u8g2); }
    void sendBuffer() {}
    void firstPage() { u8g2_FirstPage(&u8g2); }
    int nextPage() { return u8g2_NextPage(&u8g2); }
    uint8_t* getBufferPtr() { return u8g2_GetBufferPtr(&u8g2); }
    int getBufferTileWidth() { return u8g2_GetBufferTileWidth(&u8g2); }
    int getBufferTileHeight() { return u8g2_GetBufferTileHeight(&u8g2); }
    void setFont(const uint8_t* f) { u8g2_SetFont(&u8g2, f); }
    void setFontMode(int m) { u8g2_SetFontMode(&u8g2, m); }
    void setDrawColor(int c) { u8g2_SetDrawColor(&u8g2, c); }
    int drawStr(int x, int y, const char* s) { return u8g2_DrawStr(&u8g2, x, y, s); }
    int drawUTF8(int x, int y, const char* s) { return u8g2_DrawUTF8(&u8g2, x, y, s); }
    int drawGlyph(int x, int y, uint16_t g) { return u8g2_DrawGlyph(&u8g2, x, y, g); }
    int getStrWidth(const char* s) { return u8g2_GetStrWidth(&u8g2, s); }
    int getUTF8Width(const char* s) { return u8g2_GetUTF8Width(&u8g2, s); }
    int getAscent() { return u8g2_GetAscent(&u8g2); }
    int getDescent() { return u8g2_GetDescent(&u8g2); }
    void drawBox(int x, int y, int w, int h) { u8g2_DrawBox(&u8g2, x, y, w, h); }
    void drawFrame(int x, int y, int w, int h) { u8g2_DrawFrame(&u8g2, x, y, w, h); }
    void drawHLine(int x, int y, int w) { u8g2_DrawHLine(&u8g2, x, y, w); }
    void drawVLine(int x, int y, int h) { u8g2_DrawVLine(&u8g2, x, y, h); }
    void drawLine(int a, int b, int c, int d) { u8g2_DrawLine(&u8g2, a, b, c, d); }
    void drawPixel(int x, int y) { u8g2_DrawPixel(&u8g2, x, y); }
};
class U8G2_SSD1312_128X64_NONAME_F_HW_I2C : public U8G2 {
public:
    U8G2_SSD1312_128X64_NONAME_F_HW_I2C(const u8g2_cb_t* rot, uint8_t, uint8_t, uint8_t) {
        u8g2_Setup_ssd1312_i2c_128x64_noname_f(&u8g2, rot, u8x8_dummy_cb, u8x8_dummy_cb);
    }
};
using U8G2_SSD1306_128X64_NONAME_F_HW_I2C = U8G2_SSD1312_128X64_NONAME_F_HW_I2C;
