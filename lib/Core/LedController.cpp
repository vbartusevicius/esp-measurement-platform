#include "LedController.h"

LedController::LedController()
{
    this->lastState = false;
    this->lastBlink = 0;
    this->blinkDuration = 25;
    this->pendingClick = false;

    pinMode(LED_BUILTIN, OUTPUT);
}

void LedController::click()
{
    this->pendingClick = true;
}

void LedController::run()
{
    unsigned long now = millis();

    if ((this->lastBlink + this->blinkDuration) > now) {
        return;
    }

    digitalWrite(LED_BUILTIN, HIGH);

    if (this->pendingClick) {
        this->lastBlink = now;
        digitalWrite(LED_BUILTIN, LOW);
        this->pendingClick = false;
    }
}
