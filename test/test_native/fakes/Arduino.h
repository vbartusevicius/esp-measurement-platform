#pragma once

#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <cmath>
#include <string>
#include <cstdio>

typedef uint8_t byte;
typedef bool boolean;

#define HIGH 1
#define LOW  0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2

// Seeed XIAO ESP32-C6 pin names -> GPIO
#define D0 0
#define D1 1
#define D2 2
#define D3 21
#define D4 22
#define D5 23
#define D6 16
#define D7 17
#define D8 19
#define D9 20
#define D10 18

#define DEC 10
#define HEX 16
#define OCT 8
#define BIN 2

#define IRAM_ATTR
#define CHANGE 1
#define FALLING 2
#define RISING 3

namespace FakeHAL {
    inline unsigned long currentMillis = 0;
    inline int nextAnalogRead = 0;
    inline unsigned long nextPulseIn = 0;
}

inline unsigned long millis() { return FakeHAL::currentMillis; }
inline void delay(unsigned long ms) { FakeHAL::currentMillis += ms; }
inline void delayMicroseconds(unsigned int) {}
inline void pinMode(uint8_t, uint8_t) {}
inline void digitalWrite(uint8_t, uint8_t) {}
inline int  digitalRead(uint8_t) { return LOW; }
inline int  analogRead(uint8_t) { return FakeHAL::nextAnalogRead; }
inline int  analogReadMilliVolts(uint8_t) { return FakeHAL::nextAnalogRead; }
inline unsigned long pulseIn(uint8_t, uint8_t, unsigned long = 1000000) {
    return FakeHAL::nextPulseIn;
}
inline void attachInterrupt(uint8_t, void (*)(), int) {}
inline void detachInterrupt(uint8_t) {}
inline void noInterrupts() {}
inline void interrupts() {}
inline uint8_t digitalPinToInterrupt(uint8_t pin) { return pin; }

inline double dtostrf(double val, signed char width, unsigned char prec, char* sout) {
    snprintf(sout, width + prec + 2, "%*.*f", width, prec, val);
    return val;
}

class String {
    std::string _buf;
public:
    String() {}
    String(const char* s) : _buf(s ? s : "") {}
    String(const std::string& s) : _buf(s) {}
    String(int val) : _buf(std::to_string(val)) {}
    String(unsigned int val) : _buf(std::to_string(val)) {}
    String(long val) : _buf(std::to_string(val)) {}
    String(unsigned long val) : _buf(std::to_string(val)) {}
    String(unsigned long val, int base) {
        if (base == 16) {
            char buf[32]; snprintf(buf, sizeof(buf), "%lx", val);
            _buf = buf;
        } else { _buf = std::to_string(val); }
    }
    String(unsigned int val, int base) {
        if (base == 16) {
            char buf[32]; snprintf(buf, sizeof(buf), "%x", val);
            _buf = buf;
        } else { _buf = std::to_string(val); }
    }
    String(float val, int dec = 2) {
        char buf[64];
        snprintf(buf, sizeof(buf), "%.*f", dec, (double)val);
        _buf = buf;
    }
    String(double val, int dec = 2) {
        char buf[64];
        snprintf(buf, sizeof(buf), "%.*f", dec, val);
        _buf = buf;
    }

    const char* c_str() const { return _buf.c_str(); }
    unsigned int length() const { return (unsigned int)_buf.length(); }
    bool isEmpty() const { return _buf.empty(); }
    int indexOf(char c, unsigned int from = 0) const {
        size_t pos = _buf.find(c, from);
        return pos == std::string::npos ? -1 : (int)pos;
    }
    String substring(unsigned int from) const { return substring(from, (unsigned int)_buf.size()); }
    String substring(unsigned int from, unsigned int to) const {
        if (from >= _buf.size() || to <= from) return String();
        return String(_buf.substr(from, to - from).c_str());
    }
    bool endsWith(const char* suffix) const {
        std::string t(suffix ? suffix : "");
        return _buf.size() >= t.size() && _buf.compare(_buf.size() - t.size(), t.size(), t) == 0;
    }
    void trim() {
        size_t b = _buf.find_first_not_of(" \t\r\n");
        size_t e = _buf.find_last_not_of(" \t\r\n");
        _buf = b == std::string::npos ? std::string() : _buf.substr(b, e - b + 1);
    }
    int toInt() const { return atoi(_buf.c_str()); }
    float toFloat() const { return (float)atof(_buf.c_str()); }
    void toUpperCase() {
        for (auto& c : _buf) c = toupper(c);
    }

    String operator+(const String& rhs) const { return String((_buf + rhs._buf).c_str()); }
    String operator+(const char* rhs) const { return String((_buf + (rhs ? rhs : "")).c_str()); }
    String& operator+=(const String& rhs) { _buf += rhs._buf; return *this; }
    bool concat(const char* s) { if (s) _buf += s; return true; }
    bool operator==(const String& rhs) const { return _buf == rhs._buf; }
    bool operator!=(const String& rhs) const { return _buf != rhs._buf; }

    friend String operator+(const char* lhs, const String& rhs) {
        return String((std::string(lhs ? lhs : "") + rhs._buf).c_str());
    }
};

class FakeSerial {
public:
    void begin(unsigned long) {}
    void println(const char*) {}
    void println(const String&) {}
    void printf(const char*, ...) {}
    void print(const char*) {}
    void print(const String&) {}
};
inline FakeSerial Serial;

// Like the real cores, Arduino.h provides the ESP object.
class EspClass {
public:
    uint32_t freeHeap = 65536;
    uint64_t getEfuseMac() { return 0xABCDEF000000ULL; }
    void restart() {}
    uint32_t getFreeHeap() { return freeHeap; }
};
inline EspClass ESP;
