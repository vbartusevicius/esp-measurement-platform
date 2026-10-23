#ifndef LIMIT_MONITOR_H
#define LIMIT_MONITOR_H

#include <cmath>

// MIN/MAX threshold supervision with hysteresis, alert acknowledge and an
// optional relay rule. Limits are in the plugin's primary unit (% for tanks,
// bar for pressure, uSv/h for radiation). NAN disables a limit.
class LimitMonitor
{
    public:
        enum class State { NORMAL, BELOW, ABOVE };
        enum class RelayMode { MANUAL, ON_ALARM, OFF_ALARM };

        void configure(float low, float high, float hysteresis, RelayMode mode);

        // Returns true when the state changed. Invalid readings (sensor
        // fault) hold the previous state so the relay does not chatter.
        bool update(float value, bool valid);

        State state() const { return this->current; }
        bool alarm() const { return this->current != State::NORMAL; }
        bool alertPending() const { return this->alarm() && !this->acknowledged; }
        void acknowledge() { if (this->alarm()) this->acknowledged = true; }

        // false when the relay is under manual control.
        bool relayDemand(bool& on) const;
        RelayMode relayMode() const { return this->mode; }

        float low() const { return this->lowLimit; }
        float high() const { return this->highLimit; }
        bool hasLow() const { return !std::isnan(this->lowLimit); }
        bool hasHigh() const { return !std::isnan(this->highLimit); }
        float activeLimit() const { return this->current == State::BELOW ? this->lowLimit : this->highLimit; }
        unsigned long trips() const { return this->tripCount; }

        static RelayMode parseMode(const char* text);
        static const char* modeName(RelayMode mode);
        static const char* stateName(State state);

    private:
        float lowLimit = NAN;
        float highLimit = NAN;
        float hysteresis = 0.0f;
        RelayMode mode = RelayMode::MANUAL;
        State current = State::NORMAL;
        bool acknowledged = false;
        unsigned long tripCount = 0;
};

#endif
