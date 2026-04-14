#pragma once

#include "Arduino.h"
#include <string>

class JsonObject {
public:
    JsonObject operator[](const char*) { return JsonObject(); }
    void operator=(const char*) {}
    void operator=(const String&) {}
    void operator=(int) {}
    void operator=(float) {}
    void operator=(double) {}
    JsonObject to() { return JsonObject(); }
    template<typename T> T to() { return T(); }
};

class JsonDocument {
public:
    JsonObject operator[](const char*) { return JsonObject(); }
};

inline void serializeJson(JsonDocument&, String&) {}
