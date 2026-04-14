#include "LedController.h"
#include "HAL.h"

LedController::LedController()
{
    this->hal = nullptr;
    this->lastState = false;
    this->lastBlink = 0;
    this->blinkDuration = 25;
    this->pendingClick = false;
}

void LedController::begin(HAL* hal)
{
    this->hal = hal;
    this->hal->pinMode(LED_BUILTIN, OUTPUT);
}

void LedController::click()
{
    this->pendingClick = true;
}

void LedController::run()
{
    unsigned long now = this->hal->millis();

    if ((this->lastBlink + this->blinkDuration) > now) {
        return;
    }

    this->hal->digitalWrite(LED_BUILTIN, HIGH);

    if (this->pendingClick) {
        this->lastBlink = now;
        this->hal->digitalWrite(LED_BUILTIN, LOW);
        this->pendingClick = false;
    }
}
