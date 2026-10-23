#include "EventLog.h"
#include <cctype>

static void copyUpper(char* dest, const char* src)
{
    size_t i = 0;
    for (; src && src[i] && i < EventLog::TEXT_LENGTH; i++) {
        dest[i] = (char)toupper((unsigned char)src[i]);
    }
    dest[i] = '\0';
}

void EventLog::add(const char* title, const char* detail, unsigned long nowMs)
{
    Entry* entry;
    if (this->count < CAPACITY) {
        entry = &this->entries[(this->start + this->count) % CAPACITY];
        this->count++;
    } else {
        entry = &this->entries[this->start];
        this->start = (this->start + 1) % CAPACITY;
    }
    entry->uptimeSec = nowMs / 1000UL;
    copyUpper(entry->title, title);
    copyUpper(entry->detail, detail);
    this->totalAdded++;
}

const EventLog::Entry& EventLog::newest(size_t index) const
{
    return this->entries[(this->start + this->count - 1 - index) % CAPACITY];
}
