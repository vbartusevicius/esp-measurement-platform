#pragma once

#include "Arduino.h"

class EspClass {
public:
    uint32_t getChipId() { return 0xABCDEF; }
    void restart() {}
    uint32_t getFreeHeap() { return 65536; }
};

inline EspClass ESP;
