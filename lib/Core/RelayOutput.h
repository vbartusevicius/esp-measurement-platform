#ifndef RELAY_OUTPUT_H
#define RELAY_OUTPUT_H

class HAL;

// K1 changeover relay. Always off after boot (the driver's 10k base pull-down
// also holds it off while the MCU resets).
class RelayOutput
{
    private:
        HAL* hal = nullptr;
        int pin = -1;
        bool on = false;

    public:
        void begin(HAL* hal, int pin);
        void set(bool on);
        bool isOn() const { return this->on; }
        bool available() const { return this->pin >= 0; }

        // "ON"/"OFF", "1"/"0", "true"/"false" (case-insensitive); false if unrecognised.
        static bool parseCommand(const char* payload, bool& on);
};

#endif
