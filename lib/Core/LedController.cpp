#include "LedController.h"
#include <Adafruit_NeoPixel.h>
#include "Board.h"
#include "HAL.h"

namespace
{
    constexpr uint8_t LED_STATUS = 0;
    constexpr uint8_t LED_NET = 1;
    constexpr uint8_t LED_SENS = 2;
    constexpr uint8_t LEVEL = 24;   // keeps the three LEDs well inside the 600 mA 5 V budget
    constexpr unsigned long REFRESH_MS = 50;
    constexpr unsigned long SENS_FLASH_MS = 60;
    Adafruit_NeoPixel pixels(3, Board::LED_DATA_PIN, NEO_GRB + NEO_KHZ800);
}

void LedController::begin(HAL* hal)
{
    this->hal = hal;
    pixels.begin();
    pixels.clear();
    pixels.show();
}

IRAM_ATTR void LedController::click()   // called from sensor ISRs
{
    this->pendingClick = true;
}

void LedController::setNetworkState(NetState state)
{
    this->netState = state;
}

LedController::NetState LedController::netStateFor(bool wifiConnected, bool mqttConnected, bool portalActive)
{
    if (wifiConnected) return mqttConnected ? NetState::MQTT : NetState::WIFI;
    return portalActive ? NetState::PORTAL : NetState::OFFLINE;
}

void LedController::run()
{
    const unsigned long now = this->hal->millis();
    if (this->pendingClick) {
        this->sensFlashAt = now;
        this->sensOn = true;
        this->pendingClick = false;
    } else if (now - this->sensFlashAt >= SENS_FLASH_MS) {
        this->sensOn = false;
    }
    if (now - this->lastRefresh < REFRESH_MS) return;
    this->lastRefresh = now;

    const bool heartbeat = (now % 2000) < 120;
    pixels.setPixelColor(LED_STATUS, heartbeat ? pixels.Color(0, LEVEL, 0) : pixels.Color(0, 2, 0));

    uint32_t net = 0;
    switch (this->netState) {
        case NetState::OFFLINE: net = ((now / 500) % 2) ? pixels.Color(LEVEL, 0, 0) : 0; break;
        case NetState::PORTAL:  net = ((now / 250) % 2) ? pixels.Color(0, 0, LEVEL) : 0; break;
        case NetState::WIFI:    net = pixels.Color(LEVEL, LEVEL / 2, 0); break;
        case NetState::MQTT:    net = pixels.Color(0, LEVEL, 0); break;
    }
    pixels.setPixelColor(LED_NET, net);
    pixels.setPixelColor(LED_SENS, this->sensOn ? pixels.Color(LEVEL, LEVEL, LEVEL) : 0);
    pixels.show();
}
