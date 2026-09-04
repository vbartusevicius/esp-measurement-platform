#pragma once

#include "Arduino.h"
#include <vector>

// In-memory stand-in for the ESP8266 EEPROM sector. The backing store is
// static so it survives begin()/end() cycles, like real flash does.
class FakeEEPROM {
    static std::vector<uint8_t>& store() {
        static std::vector<uint8_t> data;
        return data;
    }

public:
    void begin(size_t size) {
        if (store().size() < size) store().resize(size, 0xFF);
    }
    uint8_t read(int address) {
        if (address < 0 || (size_t)address >= store().size()) return 0xFF;
        return store()[address];
    }
    void write(int address, uint8_t value) {
        if (address < 0) return;
        if ((size_t)address >= store().size()) store().resize(address + 1, 0xFF);
        store()[address] = value;
    }
    bool commit() { return true; }
    void end() {}
};

inline FakeEEPROM EEPROM;
