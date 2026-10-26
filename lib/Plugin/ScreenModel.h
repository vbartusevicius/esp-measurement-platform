#ifndef SCREEN_MODEL_H
#define SCREEN_MODEL_H

#include <Arduino.h>
#include <cmath>
#include <vector>

struct ScreenLine {
    const char* label;
    String value;
};

// Plugin-independent view of the primary measurement. One source for the
// OLED pages (main + STAT) and the WebUI, so both always show the same data.
struct ScreenModel {
    const char* kind = "";           // level | pressure | radiation | voltage | water: picks the web UI view
    const char* title = "";          // header, max 4 chars: TANK / PRES / RAD
    float value = NAN;               // primary value, also what MIN/MAX limits compare
    const char* unit = "";           // unit of value, limits, trend and 24 h extremes
    int decimals = 0;
    bool valid = false;              // value is a real reading (sensor OK, warmed up)

    float scaleMin = NAN;            // chart/gauge axis, NAN = auto from data
    float scaleMax = NAN;
    std::vector<float> trend;        // oldest first, same unit as value
    unsigned long trendBucketSec = 0;

    std::vector<ScreenLine> lines;   // two secondary readings under the chart
    const char* sensorLabel = "SENS";
    bool sensorOk = false;

    String raw;                      // unfiltered physical reading (web / MQTT)
    String signal;                   // terminal signal: mA / V / pulses
    float low24 = NAN;
    float high24 = NAN;
    // Two OLED diagnostic rows under the sensor state; empty = 24 h low / high
    std::vector<ScreenLine> details;

    String format(float v) const
    {
        if (std::isnan(v)) return String("--");
        return String(v, this->decimals);
    }
};

#endif
