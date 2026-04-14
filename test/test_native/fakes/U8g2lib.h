#pragma once

#include <cstdint>
#include <cstring>

inline const uint8_t u8g2_font_5x7_tr[] = {0};
inline const uint8_t u8g2_font_6x10_tr[] = {0};
inline const uint8_t u8g2_font_6x12_mf[] = {0};

class U8G2 {
public:
    void drawFrame(int, int, int, int) {}
    void drawBox(int, int, int, int) {}
    void drawStr(int, int, const char*) {}
    void drawUTF8(int, int, const char*) {}
    void drawLine(int, int, int, int) {}
    void drawVLine(int, int, int) {}
    void drawPixel(int, int) {}
    int  getStrWidth(const char* s) { return s ? (int)strlen(s) * 5 : 0; }
    int  getUTF8Width(const char* s) { return s ? (int)strlen(s) * 5 : 0; }
    int  getAscent() { return 7; }
    int  getDescent() { return -2; }
    void setFont(const uint8_t*) {}
    void setFontMode(int) {}
    void setDrawColor(int) {}
    void clearBuffer() {}
    void sendBuffer() {}
};
