#include "Storage.h"
#include <EEPROM.h>

// Layout: magic (4B) | count (2B) | count x { keyLen (1B) | valLen (1B) | key | value }

Storage::Storage()
{
}

void Storage::begin()
{
    this->load();
}

void Storage::load()
{
    this->entries.clear();

    EEPROM.begin(EEPROM_SIZE);

    uint32_t magic = 0;
    for (int i = 0; i < 4; i++) {
        magic |= (uint32_t)EEPROM.read(i) << (8 * i);
    }

    if (magic != MAGIC) {
        EEPROM.end();
        return;  // never written: no configuration yet
    }

    uint16_t count = EEPROM.read(4) | ((uint16_t)EEPROM.read(5) << 8);
    size_t addr = 6;

    for (uint16_t i = 0; i < count; i++) {
        if (addr + 2 > EEPROM_SIZE) break;

        uint8_t keyLen = EEPROM.read(addr++);
        uint8_t valLen = EEPROM.read(addr++);
        if (addr + keyLen + valLen > EEPROM_SIZE) break;

        char keyBuf[64] = {0};
        char valBuf[128] = {0};
        if (keyLen >= sizeof(keyBuf) || valLen >= sizeof(valBuf)) break;

        for (uint8_t k = 0; k < keyLen; k++) keyBuf[k] = (char)EEPROM.read(addr++);
        for (uint8_t v = 0; v < valLen; v++) valBuf[v] = (char)EEPROM.read(addr++);

        this->entries.push_back({String(keyBuf), String(valBuf)});
    }

    EEPROM.end();
}

bool Storage::persist()
{
    // Size check before touching flash so a partial write is impossible
    size_t needed = 6;
    for (auto& e : this->entries) {
        needed += 2 + e.key.length() + e.value.length();
    }
    if (needed > EEPROM_SIZE) return false;

    EEPROM.begin(EEPROM_SIZE);

    for (int i = 0; i < 4; i++) {
        EEPROM.write(i, (uint8_t)((MAGIC >> (8 * i)) & 0xFF));
    }

    uint16_t count = (uint16_t)this->entries.size();
    EEPROM.write(4, (uint8_t)(count & 0xFF));
    EEPROM.write(5, (uint8_t)(count >> 8));

    size_t addr = 6;
    for (auto& e : this->entries) {
        EEPROM.write(addr++, (uint8_t)e.key.length());
        EEPROM.write(addr++, (uint8_t)e.value.length());
        const char* key = e.key.c_str();
        const char* value = e.value.c_str();
        for (size_t k = 0; k < e.key.length(); k++) EEPROM.write(addr++, (uint8_t)key[k]);
        for (size_t v = 0; v < e.value.length(); v++) EEPROM.write(addr++, (uint8_t)value[v]);
    }

    bool ok = EEPROM.commit();
    EEPROM.end();
    return ok;
}

Storage::Entry* Storage::find(const char* name)
{
    for (auto& e : this->entries) {
        if (e.key == name) return &e;
    }
    return nullptr;
}

void Storage::saveParameter(const char* name, const String& value)
{
    Entry* existing = this->find(name);
    if (existing) {
        if (existing->value == value) return;  // no flash write when unchanged
        existing->value = value;
    } else {
        this->entries.push_back({String(name), value});
    }
    this->persist();
}

String Storage::getParameter(const char* name, String defaultValue)
{
    Entry* existing = this->find(name);
    return existing ? existing->value : defaultValue;
}

bool Storage::hasParameter(const char* name)
{
    return this->find(name) != nullptr;
}

void Storage::reset()
{
    this->entries.clear();
    this->persist();
}
