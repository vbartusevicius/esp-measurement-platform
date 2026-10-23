#ifndef BOARD_H
#define BOARD_H

#include <Arduino.h>

// Pin map and analog front-end of the ESP Measurement Platform v1 board
// (XIAO ESP32-C6, hardware/product/spec.yaml derived.mcu_pins).
namespace Board
{
    constexpr const char* MODEL = "ESP Measurement Platform v1 (XIAO ESP32-C6)";

    constexpr int V0_10_PIN = D0;           // GPIO0 / ADC1_CH0, 22k / 10k divider (J2.5)
    constexpr int MA_PIN = D1;              // GPIO1 / ADC1_CH1, 120R shunt after a 50 mA PTC (J2.4)
    constexpr int BUTTON_LADDER_PIN = D2;   // GPIO2 / ADC1_CH2, RST/WIFI + PAGE on the UI board
    constexpr int LED_DATA_PIN = D3;        // GPIO21, 3x SK6805-EC15 via 74AHCT1G125
    constexpr int I2C_SDA_PIN = D4;         // GPIO22, OLED
    constexpr int I2C_SCL_PIN = D5;         // GPIO23, OLED
    constexpr int IO2_PIN = D6;             // GPIO16 (J2.7): SCL / TX / TRIG
    constexpr int IO1_PIN = D7;             // GPIO17 (J2.6): SDA / RX / PULSE / ECHO
    constexpr int RELAY_PIN = D8;           // GPIO19, K1 driver (active high)

    constexpr float MA_SHUNT_OHMS = 120.0f;
    constexpr float V0_10_DIVIDER = (22.0f + 10.0f) / 10.0f;

    constexpr int TRIG_PIN = IO2_PIN;
    constexpr int ECHO_PIN = IO1_PIN;
    constexpr int PULSE_PIN = IO1_PIN;
}

#endif
