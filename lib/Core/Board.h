#ifndef BOARD_H
#define BOARD_H

#include <Arduino.h>

// Pin map and analog front-end of the hardware the firmware is built for.
// BOARD_XIAO_ESP32C6: ESP Measurement Platform v1 (hardware/product/spec.yaml
// derived.mcu_pins). Otherwise: NodeMCU ESP8266 with external sensor wiring.
namespace Board
{
#if defined(BOARD_XIAO_ESP32C6)
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

    constexpr int ANALOG_PIN = MA_PIN;
    constexpr int TRIG_PIN = IO2_PIN;
    constexpr int ECHO_PIN = IO1_PIN;
    constexpr int PULSE_PIN = IO1_PIN;
    constexpr int PAGE_BUTTON_PIN = -1;     // buttons are on the ADC ladder
#else
    constexpr const char* MODEL = "ESP8266";

    constexpr int ANALOG_PIN = A0;          // external 4-20 mA -> 0-3.3 V converter
    constexpr int TRIG_PIN = D1;
    constexpr int ECHO_PIN = D2;
    constexpr int PULSE_PIN = D2;
    constexpr int PAGE_BUTTON_PIN = 0;      // NodeMCU FLASH button

    constexpr float MA_SHUNT_OHMS = 0.0f;   // no on-board shunt
    constexpr int V0_10_PIN = A0;           // shared with ANALOG_PIN; 0-3.3 V (NodeMCU on-board divider), add a divider for 5/10 V sensors
    constexpr float V0_10_DIVIDER = 1.0f;

    constexpr int RELAY_PIN = -1;           // no relay: RelayOutput stays unavailable
#endif
}

#endif
