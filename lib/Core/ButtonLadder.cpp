#include "ButtonLadder.h"

ButtonLadder::Button ButtonLadder::classify(int millivolts)
{
    if (millivolts > 2750) return Button::NONE;
    if (millivolts > 1930) return Button::CROSS;
    if (millivolts > 1490) return Button::DOT;
    if (millivolts > 1000) return Button::BOTH;
    return Button::NONE;
}

ButtonLadder::Event ButtonLadder::update(int millivolts, unsigned long nowMs)
{
    Button reading = classify(millivolts);
    if (reading != this->candidate) {
        this->candidate = reading;
        return Event::NONE;
    }
    if (reading == this->stable) {
        if (reading == Button::CROSS && !this->crossHeldReported && nowMs - this->crossPressedAt >= CROSS_HOLD_MS) {
            this->crossHeldReported = true;
            return Event::CROSS_HELD;
        }
        if (reading == Button::CROSS && !this->factoryReported && nowMs - this->crossPressedAt >= FACTORY_HOLD_MS) {
            this->factoryReported = true;
            return Event::CROSS_FACTORY;
        }
        return Event::NONE;
    }

    Button previous = this->stable;
    this->stable = reading;

    if (reading == Button::CROSS) {
        this->crossPressedAt = nowMs;
        this->crossHeldReported = false;
        this->factoryReported = false;
    }
    if (previous == Button::CROSS && reading == Button::NONE && !this->crossHeldReported) {
        return Event::CROSS_TAPPED;
    }
    if (reading == Button::DOT && previous == Button::NONE) {
        return Event::DOT_PRESSED;
    }
    return Event::NONE;
}
