#ifndef SCOPED_SETTINGS_H
#define SCOPED_SETTINGS_H

#include "Settings.h"

// One sensor's view of the device settings: every key gets the sensor's
// prefix ("ad." for analog_distance), so sensors running side by side keep
// their own distance_empty, sampling_interval, limits and so on.
class ScopedSettings : public Settings
{
    public:
        ScopedSettings(Settings* base, const String& prefix) : base(base), scope(prefix) {}

        String getParameter(const char* name, String defaultValue = String()) const override;
        void saveParameter(const char* name, const String& value) override;
        bool hasParameter(const char* name) const override;

        const String& prefix() const { return this->scope; }
        // Initials of the plugin id's words plus a dot: "pulse_meter" -> "pm."
        static String prefixFor(const char* pluginId);

    private:
        Settings* base;
        String scope;

        String key(const char* name) const { return this->scope + name; }
};

#endif
