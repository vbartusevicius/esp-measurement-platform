#include "Storage.h"
#include "Parameter.h"
#include "IPlugin.h"

Storage::Storage()
{
}

void Storage::begin()
{
    prefs.begin("esp_unified");
}

void Storage::saveParameter(const char* name, String& value)
{
    prefs.putString(name, value);
}

String Storage::getParameter(const char* name, String defaultValue)
{
    return prefs.getString(name, defaultValue);
}

bool Storage::isEmpty(IPlugin* activePlugin)
{
    // Core required parameters
    if (!prefs.isKey(Parameter::MQTT_HOST)) return true;
    if (!prefs.isKey(Parameter::MQTT_PORT)) return true;
    if (!prefs.isKey(Parameter::MQTT_DEVICE)) return true;

    // Plugin-specific required parameters
    if (activePlugin) {
        auto required = activePlugin->getRequiredParameters();
        for (auto& param : required) {
            if (!prefs.isKey(param)) return true;
        }
    }

    return false;
}

void Storage::reset()
{
    prefs.clear();
}
