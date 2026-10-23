#pragma once

#include "Arduino.h"

#define NEO_GRB 0x52
#define NEO_KHZ800 0x0000

// Records nothing: LedController's colour logic is exercised through its pure helpers.
class Adafruit_NeoPixel {
public:
    Adafruit_NeoPixel(uint16_t, int16_t, uint16_t) {}
    void begin() {}
    void clear() {}
    void show() {}
    void setPixelColor(uint16_t, uint32_t) {}
    static uint32_t Color(uint8_t r, uint8_t g, uint8_t b) { return ((uint32_t)r << 16) | ((uint32_t)g << 8) | b; }
};
