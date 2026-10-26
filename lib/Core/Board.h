#ifndef BOARD_H
#define BOARD_H

#include <Arduino.h>

// Pin map and analog front-end of the ESP Measurement Platform v1 board
// (XIAO ESP32-C6, hardware/product/spec.yaml derived.mcu_pins).
namespace Board
{
    constexpr const char* MODEL = "ESP Measurement Platform v1 (XIAO ESP32-C6)";

    constexpr int V0_10_PIN = D0;           // GPIO0 / ADC1_CH0, 22k / 10k divider (J2 pole 4)
    constexpr int MA_PIN = D1;              // GPIO1 / ADC1_CH1, 120R shunt after a 50 mA PTC (J2 pole 3)
    constexpr int BUTTON_LADDER_PIN = D2;   // GPIO2 / ADC1_CH2, RST/WIFI + PAGE on the UI board
    constexpr int LED_DATA_PIN = D3;        // GPIO21, 3x SK6805-EC15 via 74AHCT1G125
    constexpr int I2C_SDA_PIN = D4;         // GPIO22, OLED
    constexpr int I2C_SCL_PIN = D5;         // GPIO23, OLED
    constexpr int IO2_PIN = D6;             // GPIO16 (J2 pole 6): TRIG / SCL / TX
    constexpr int IO1_PIN = D7;             // GPIO17 (J2 pole 5): ECHO / SDA / RX
    constexpr int RELAY_PIN = D8;           // GPIO19, K1 driver (active high)
    constexpr int IO3_PIN = D9;             // GPIO20 (J2 pole 7): Geiger PULSE
    constexpr int IO4_PIN = D10;            // GPIO18 (J2 pole 8): meter pulse (open collector)

    constexpr float MA_SHUNT_OHMS = 120.0f;
    constexpr float V0_10_DIVIDER = (22.0f + 10.0f) / 10.0f;

    constexpr int TRIG_PIN = IO2_PIN;
    constexpr int ECHO_PIN = IO1_PIN;
    // Sensor-bank inputs a plugin can claim (IPlugin::inputs), with their pole numbers
    enum Input : uint8_t {
        INPUT_MA = 1 << 0,    // pole 3, 4-20 mA
        INPUT_V = 1 << 1,     // pole 4, 0-10 V
        INPUT_IO1 = 1 << 2,   // pole 5
        INPUT_IO2 = 1 << 3,   // pole 6
        INPUT_IO3 = 1 << 4,   // pole 7
        INPUT_IO4 = 1 << 5,   // pole 8
    };

    constexpr int PULSE_PIN = IO3_PIN;
    constexpr int METER_PULSE_PIN = IO4_PIN;
}

#endif
