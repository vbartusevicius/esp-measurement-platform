#ifndef STORAGE_H
#define STORAGE_H

#include <Preferences.h>
#include <vector>

class IPlugin;

class Storage
{
    private:
        Preferences prefs;

    public:
        Storage();
        void begin();
        void saveParameter(const char* name, String& value);
        String getParameter(const char* name, String defaultValue = String());
        bool isEmpty(IPlugin* activePlugin);
        void reset();
};

#endif
