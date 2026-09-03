#ifndef STORAGE_H
#define STORAGE_H

#include <Preferences.h>

class Storage
{
    private:
        Preferences prefs;

    public:
        Storage();
        void begin();
        void saveParameter(const char* name, const String& value);
        String getParameter(const char* name, String defaultValue = String());
        bool hasParameter(const char* name);
        void reset();
};

#endif
