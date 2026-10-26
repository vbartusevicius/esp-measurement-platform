#ifndef STORAGE_H
#define STORAGE_H

#include <Arduino.h>
#include <vector>
#include "Settings.h"

// All device settings in one EEPROM-emulation blob. An empty value removes
// its key (reads give the default again), so unused form fields cost nothing.
class Storage : public Settings
{
    private:
        // Five sensors with every setting and limit filled in need ~2.2 KB (test_sensor_hub).
        static constexpr size_t EEPROM_SIZE = 3072;
        static constexpr uint32_t MAGIC = 0x45535031;  // "ESP1"

        struct Entry {
            String key;
            String value;
        };

        std::vector<Entry> entries;

        Entry* find(const char* name);
        const Entry* find(const char* name) const;
        void load();
        bool persist();

    public:
        void begin();
        void saveParameter(const char* name, const String& value) override;
        String getParameter(const char* name, String defaultValue = String()) const override;
        bool hasParameter(const char* name) const override;
        void reset();
        // Bytes the blob would need, against its EEPROM_SIZE capacity
        size_t usedBytes() const;
        static constexpr size_t capacity() { return EEPROM_SIZE; }
};

#endif
