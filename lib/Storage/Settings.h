#ifndef SETTINGS_H
#define SETTINGS_H

#include <Arduino.h>

// Key/value settings as plugins and the limit monitor see them: the device
// Storage itself, or a ScopedSettings view that keeps one sensor's keys apart.
class Settings
{
    public:
        virtual ~Settings() = default;
        virtual String getParameter(const char* name, String defaultValue = String()) const = 0;
        virtual void saveParameter(const char* name, const String& value) = 0;
        virtual bool hasParameter(const char* name) const = 0;
};

#endif
