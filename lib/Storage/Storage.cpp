#include "Storage.h"

Storage::Storage()
{
}

void Storage::begin()
{
    prefs.begin("esp_unified");
}

void Storage::saveParameter(const char* name, const String& value)
{
    prefs.putString(name, value);
}

String Storage::getParameter(const char* name, String defaultValue)
{
    return prefs.getString(name, defaultValue);
}

bool Storage::hasParameter(const char* name)
{
    return prefs.isKey(name);
}

void Storage::reset()
{
    prefs.clear();
}
