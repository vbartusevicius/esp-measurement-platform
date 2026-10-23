#ifndef BUTTON_LADDER_H
#define BUTTON_LADDER_H

// Two buttons on one ADC pin (UI board): 10k pull-up to 3.3 V,
// RST/WIFI -> 20k to GND (2.20 V), PAGE -> 10k to GND (1.65 V), both 1.32 V.
class ButtonLadder
{
    public:
        enum class Button { NONE, RESET, PAGE, BOTH };
        enum class Event { NONE, PAGE_PRESSED, RESET_TAPPED, RESET_HELD };

        static constexpr unsigned long RESET_HOLD_MS = 5000;

        static Button classify(int millivolts);

        Event update(int millivolts, unsigned long nowMs);

    private:
        Button candidate = Button::NONE;
        Button stable = Button::NONE;
        unsigned long resetPressedAt = 0;
        bool resetHeldReported = false;
};

#endif
