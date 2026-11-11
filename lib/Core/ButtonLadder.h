#ifndef BUTTON_LADDER_H
#define BUTTON_LADDER_H

// Two buttons on one ADC pin (UI board), named by the mark on their cover pad:
// CROSS (X: reboot / WiFi setup / factory reset) -> 20k to GND (2.20 V),
// DOT (plain dot: next page, acknowledge an alert) -> 10k to GND (1.65 V), both 1.32 V.
// 10k pull-up to 3.3 V.
class ButtonLadder
{
    public:
        enum class Button { NONE, CROSS, DOT, BOTH };
        enum class Event { NONE, DOT_PRESSED, CROSS_TAPPED, CROSS_HELD, CROSS_FACTORY };

        // CROSS_HELD (WiFi setup portal) fires at 5 s while still held,
        // CROSS_FACTORY at 15 s.
        static constexpr unsigned long CROSS_HOLD_MS = 5000;
        static constexpr unsigned long FACTORY_HOLD_MS = 15000;

        static Button classify(int millivolts);

        Event update(int millivolts, unsigned long nowMs);

    private:
        Button candidate = Button::NONE;
        Button stable = Button::NONE;
        unsigned long crossPressedAt = 0;
        bool crossHeldReported = false;
        bool factoryReported = false;
};

#endif
