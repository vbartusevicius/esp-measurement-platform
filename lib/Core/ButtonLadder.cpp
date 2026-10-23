#include "ButtonLadder.h"

ButtonLadder::Button ButtonLadder::classify(int millivolts)
{
    if (millivolts > 2750) return Button::NONE;
    if (millivolts > 1930) return Button::RESET;
    if (millivolts > 1490) return Button::PAGE;
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
        if (reading == Button::RESET && !this->resetHeldReported && nowMs - this->resetPressedAt >= RESET_HOLD_MS) {
            this->resetHeldReported = true;
            return Event::RESET_HELD;
        }
        return Event::NONE;
    }

    Button previous = this->stable;
    this->stable = reading;

    if (reading == Button::RESET) {
        this->resetPressedAt = nowMs;
        this->resetHeldReported = false;
    }
    if (previous == Button::RESET && reading == Button::NONE && !this->resetHeldReported) {
        return Event::RESET_TAPPED;
    }
    if (reading == Button::PAGE && previous == Button::NONE) {
        return Event::PAGE_PRESSED;
    }
    return Event::NONE;
}
