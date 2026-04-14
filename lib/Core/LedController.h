#ifndef LED_CONTROLLER_H
#define LED_CONTROLLER_H

#include <Arduino.h>

class HAL;

class LedController
{
    private:
        HAL* hal;
        bool lastState;
        unsigned long lastBlink;
        unsigned long blinkDuration;
        bool pendingClick;

    public:
        LedController();
        void begin(HAL* hal);
        void run();
        void click();
};

#endif
