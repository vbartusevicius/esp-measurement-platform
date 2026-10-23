#include "ChipId.h"

String ChipId::get()
{
    uint32_t chipId = static_cast<uint32_t>(ESP.getEfuseMac() >> 24);
    String id = String(chipId, HEX);
    id.toUpperCase();
    return id;
}
