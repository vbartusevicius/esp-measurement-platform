#pragma once

#include "Arduino.h"
#include <string>
#include <vector>

class MQTTClient {
public:
    MQTTClient(int bufSize = 256) {}
    void begin(const char*, int, void*) {}
    bool connect(const char*, const char* = nullptr, const char* = nullptr) { return true; }
    bool connected() { return false; }
    bool loop() { return true; }
    struct Message { std::string topic; std::string payload; bool retained; int qos; };
    std::vector<Message> published;   // recorded for assertions

    bool publish(const char* topic, const char* payload, bool retained = false, int qos = 0) {
        published.push_back({topic, payload ? payload : "", retained, qos});
        return true;
    }
    bool subscribe(const char*, int = 0) { return true; }
    void disconnect() {}
};
