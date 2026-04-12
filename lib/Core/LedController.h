#ifndef LED_CONTROLLER_H
#define LED_CONTROLLER_H

#include <Arduino.h>

class LedController
{
    private:
        bool lastState;
        unsigned long lastBlink;
        unsigned long blinkDuration;
        bool pendingClick;

    public:
        LedController();
        void run();
        void click();
};

#endif
