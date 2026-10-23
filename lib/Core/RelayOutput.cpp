#include "RelayOutput.h"
#include "HAL.h"
#include <cctype>
#include <cstring>

bool RelayOutput::parseCommand(const char* payload, bool& on)
{
    if (!payload) return false;
    char word[8] = {0};
    size_t n = 0;
    for (const char* p = payload; *p && n < sizeof(word) - 1; ++p) {
        if (!std::isspace(static_cast<unsigned char>(*p))) word[n++] = static_cast<char>(std::toupper(static_cast<unsigned char>(*p)));
    }
    if (!strcmp(word, "ON") || !strcmp(word, "1") || !strcmp(word, "TRUE")) { on = true; return true; }
    if (!strcmp(word, "OFF") || !strcmp(word, "0") || !strcmp(word, "FALSE")) { on = false; return true; }
    return false;
}

void RelayOutput::begin(HAL* hal, int pin)
{
    this->hal = hal;
    this->pin = pin;
    if (pin < 0) return;
    this->hal->digitalWrite(pin, LOW);
    this->hal->pinMode(pin, OUTPUT);
    this->on = false;
}

void RelayOutput::set(bool on)
{
    if (this->pin < 0) return;
    this->hal->digitalWrite(this->pin, on ? HIGH : LOW);
    this->on = on;
}
