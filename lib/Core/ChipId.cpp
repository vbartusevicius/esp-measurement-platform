#include "ChipId.h"

String ChipId::get()
{
#if defined(ESP32)
    uint32_t chipId = static_cast<uint32_t>(ESP.getEfuseMac() >> 24);
#else
    uint32_t chipId = ESP.getChipId();
#endif
    String id = String(chipId, HEX);
    id.toUpperCase();
    return id;
}
