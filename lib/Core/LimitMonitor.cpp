#include "LimitMonitor.h"
#include <cstring>

void LimitMonitor::configure(float low, float high, float hysteresis, RelayMode mode)
{
    this->lowLimit = low;
    this->highLimit = high;
    this->hysteresis = (std::isnan(hysteresis) || hysteresis < 0.0f) ? 0.0f : hysteresis;
    this->mode = mode;
    this->current = State::NORMAL;
    this->acknowledged = false;
}

bool LimitMonitor::update(float value, bool valid)
{
    if (!valid || std::isnan(value)) return false;

    State next = this->current;
    switch (this->current) {
        case State::NORMAL:
            if (this->hasLow() && value < this->lowLimit) next = State::BELOW;
            else if (this->hasHigh() && value > this->highLimit) next = State::ABOVE;
            break;
        case State::BELOW:
            if (!this->hasLow() || value >= this->lowLimit + this->hysteresis) next = State::NORMAL;
            break;
        case State::ABOVE:
            if (!this->hasHigh() || value <= this->highLimit - this->hysteresis) next = State::NORMAL;
            break;
    }
    // A reading can jump straight across both limits between samples.
    if (next == State::NORMAL && this->current != State::NORMAL) {
        if (this->hasLow() && value < this->lowLimit) next = State::BELOW;
        else if (this->hasHigh() && value > this->highLimit) next = State::ABOVE;
    }

    if (next == this->current) return false;
    if (this->current == State::NORMAL) this->tripCount++;
    this->current = next;
    this->acknowledged = false;
    return true;
}

bool LimitMonitor::relayDemand(bool& on) const
{
    if (this->mode == RelayMode::MANUAL) return false;
    on = (this->mode == RelayMode::ON_ALARM) == this->alarm();
    return true;
}

LimitMonitor::RelayMode LimitMonitor::parseMode(const char* text)
{
    if (text && strcmp(text, "on_alarm") == 0) return RelayMode::ON_ALARM;
    if (text && strcmp(text, "off_alarm") == 0) return RelayMode::OFF_ALARM;
    return RelayMode::MANUAL;
}

const char* LimitMonitor::modeName(RelayMode mode)
{
    switch (mode) {
        case RelayMode::ON_ALARM: return "on_alarm";
        case RelayMode::OFF_ALARM: return "off_alarm";
        default: return "manual";
    }
}

const char* LimitMonitor::stateName(State state)
{
    switch (state) {
        case State::BELOW: return "low";
        case State::ABOVE: return "high";
        default: return "normal";
    }
}
