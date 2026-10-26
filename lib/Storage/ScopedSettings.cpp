#include "ScopedSettings.h"

String ScopedSettings::getParameter(const char* name, String defaultValue) const
{
    return this->base->getParameter(this->key(name).c_str(), defaultValue);
}

void ScopedSettings::saveParameter(const char* name, const String& value)
{
    this->base->saveParameter(this->key(name).c_str(), value);
}

bool ScopedSettings::hasParameter(const char* name) const
{
    return this->base->hasParameter(this->key(name).c_str());
}

String ScopedSettings::prefixFor(const char* pluginId)
{
    String prefix;
    bool wordStart = true;
    for (const char* c = pluginId; *c; c++) {
        if (*c == '_') {
            wordStart = true;
        } else if (wordStart) {
            const char letter[2] = {*c, '\0'};
            prefix += String(letter);
            wordStart = false;
        }
    }
    return prefix + ".";
}
