#pragma once

#include "Arduino.h"
#include <map>
#include <string>

class Preferences {
    std::map<std::string, std::string> _data;
public:
    bool begin(const char*, bool = false) { return true; }
    void end() {}

    bool putString(const char* key, const String& value) {
        _data[key] = value.c_str();
        return true;
    }

    String getString(const char* key, const String& defaultValue = String()) {
        auto it = _data.find(key);
        return it != _data.end() ? String(it->second.c_str()) : defaultValue;
    }

    bool isKey(const char* key) { return _data.count(key) > 0; }
    bool clear() { _data.clear(); return true; }
};
