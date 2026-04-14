#pragma once

#include "Arduino.h"

class MQTTClient {
public:
    MQTTClient(int bufSize = 256) {}
    void begin(const char*, int, void*) {}
    bool connect(const char*, const char* = nullptr, const char* = nullptr) { return true; }
    bool connected() { return false; }
    bool loop() { return true; }
    bool publish(const char*, const char*, bool = false, int = 0) { return true; }
    bool subscribe(const char*, int = 0) { return true; }
    void disconnect() {}
};
