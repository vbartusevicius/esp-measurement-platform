#ifndef HAL_H
#define HAL_H

#include <Arduino.h>

class HAL
{
    public:
        virtual ~HAL() = default;

        virtual void pinMode(uint8_t pin, uint8_t mode) { ::pinMode(pin, mode); }
        virtual void digitalWrite(uint8_t pin, uint8_t val) { ::digitalWrite(pin, val); }
        virtual int digitalRead(uint8_t pin) { return ::digitalRead(pin); }
        virtual int analogRead(uint8_t pin) { return ::analogRead(pin); }
        virtual unsigned long pulseIn(uint8_t pin, uint8_t state, unsigned long timeout) { return ::pulseIn(pin, state, timeout); }
        virtual void delayMicroseconds(unsigned int us) { ::delayMicroseconds(us); }
        virtual unsigned long millis() { return ::millis(); }
        virtual void attachInterrupt(uint8_t interruptNum, void (*userFunc)(), int mode) { ::attachInterrupt(interruptNum, userFunc, mode); }
        virtual void detachInterrupt(uint8_t interruptNum) { ::detachInterrupt(interruptNum); }
        virtual uint8_t pinToInterrupt(uint8_t pin) { return digitalPinToInterrupt(pin); }
};

#endif
