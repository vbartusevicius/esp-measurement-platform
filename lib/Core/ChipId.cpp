#include "ChipId.h"
#include <ESP8266WiFi.h>

String ChipId::get()
{
    uint32_t chipId = ESP.getChipId();
    String id = String(chipId, HEX);
    id.toUpperCase();
    return id;
}
