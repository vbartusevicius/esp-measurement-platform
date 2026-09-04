#ifndef STORAGE_H
#define STORAGE_H

#include <Arduino.h>
#include <vector>

class Storage
{
    private:
        static constexpr size_t EEPROM_SIZE = 2048;
        static constexpr uint32_t MAGIC = 0x45535031;  // "ESP1"

        struct Entry {
            String key;
            String value;
        };

        std::vector<Entry> entries;

        Entry* find(const char* name);
        void load();
        bool persist();

    public:
        Storage();
        void begin();
        void saveParameter(const char* name, const String& value);
        String getParameter(const char* name, String defaultValue = String());
        bool hasParameter(const char* name);
        void reset();
};

#endif
