#include "LedController.h"
#include "HAL.h"
#include "Board.h"

#if defined(BOARD_XIAO_ESP32C6)
#include <Adafruit_NeoPixel.h>

namespace
{
    constexpr uint8_t LED_STATUS = 0;
    constexpr uint8_t LED_NET = 1;
    constexpr uint8_t LED_SENS = 2;
    constexpr uint8_t LEVEL = 24;   // keeps the three LEDs well inside the 600 mA 5 V budget
    constexpr unsigned long REFRESH_MS = 50;
    Adafruit_NeoPixel pixels(3, Board::LED_DATA_PIN, NEO_GRB + NEO_KHZ800);
}
#endif

LedController::LedController()
{
    this->hal = nullptr;
    this->lastState = false;
    this->lastBlink = 0;
    this->blinkDuration = 25;
    this->pendingClick = false;
    this->netState = NetState::OFFLINE;
    this->lastRefresh = 0;
}

void LedController::begin(HAL* hal)
{
    this->hal = hal;
#if defined(BOARD_XIAO_ESP32C6)
    this->blinkDuration = 60;
    pixels.begin();
    pixels.clear();
    pixels.show();
#else
    this->hal->pinMode(LED_BUILTIN, OUTPUT);
#endif
}

void LedController::click()
{
    this->pendingClick = true;
}

void LedController::setNetworkState(NetState state)
{
    this->netState = state;
}

void LedController::run()
{
    unsigned long now = this->hal->millis();

    if (this->pendingClick) {
        this->lastBlink = now;
        this->pendingClick = false;
        this->lastState = true;
    } else if ((this->lastBlink + this->blinkDuration) <= now) {
        this->lastState = false;
    }

#if defined(BOARD_XIAO_ESP32C6)
    this->refreshRgb(now);
#else
    this->hal->digitalWrite(LED_BUILTIN, this->lastState ? LOW : HIGH);  // active low
#endif
}

void LedController::refreshRgb(unsigned long now)
{
#if defined(BOARD_XIAO_ESP32C6)
    if (now - this->lastRefresh < REFRESH_MS) return;
    this->lastRefresh = now;

    bool heartbeat = (now % 2000) < 120;
    pixels.setPixelColor(LED_STATUS, heartbeat ? pixels.Color(0, LEVEL, 0) : pixels.Color(0, 2, 0));

    uint32_t net = 0;
    switch (this->netState) {
        case NetState::OFFLINE: net = ((now / 500) % 2) ? pixels.Color(LEVEL, 0, 0) : 0; break;
        case NetState::PORTAL:  net = ((now / 250) % 2) ? pixels.Color(0, 0, LEVEL) : 0; break;
        case NetState::WIFI:    net = pixels.Color(LEVEL, LEVEL / 2, 0); break;
        case NetState::MQTT:    net = pixels.Color(0, LEVEL, 0); break;
    }
    pixels.setPixelColor(LED_NET, net);
    pixels.setPixelColor(LED_SENS, this->lastState ? pixels.Color(LEVEL, LEVEL, LEVEL) : 0);
    pixels.show();
#else
    (void)now;
#endif
}
