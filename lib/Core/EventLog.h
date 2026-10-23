#ifndef EVENT_LOG_H
#define EVENT_LOG_H

#include <cstddef>

// Short two-line device events for the OLED LOG page and the WebUI
// (12 characters per line = the 64 px portrait width in a 4x6 font).
class EventLog
{
    public:
        static constexpr size_t CAPACITY = 16;
        static constexpr size_t TEXT_LENGTH = 12;

        struct Entry {
            unsigned long uptimeSec = 0;
            char title[TEXT_LENGTH + 1] = {};
            char detail[TEXT_LENGTH + 1] = {};
        };

        void add(const char* title, const char* detail, unsigned long nowMs);
        size_t size() const { return this->count; }
        unsigned long total() const { return this->totalAdded; }

        // 0 = newest.
        const Entry& newest(size_t index) const;

    private:
        Entry entries[CAPACITY];
        size_t start = 0;
        size_t count = 0;
        unsigned long totalAdded = 0;
};

#endif
