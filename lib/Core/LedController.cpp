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

    if (this->pendingClick) {
        this->lastBlink = now;
        this->hal->digitalWrite(LED_BUILTIN, LOW);  // Turn LED on (active low)
        this->pendingClick = false;
    } else if ((this->lastBlink + this->blinkDuration) <= now) {
        this->hal->digitalWrite(LED_BUILTIN, HIGH);  // Turn LED off (active low)
    }
}
