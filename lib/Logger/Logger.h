#ifndef LOGGER_H
#define LOGGER_H

#include <Arduino.h>

// Fixed-size circular buffer of log lines (oldest first).
// Avoids vector erase-from-front heap churn on every log call.
class LogBuffer
{
    public:
        static const size_t CAPACITY = 50;

        void add(const String& entry);
        size_t size() const { return count; }
        bool empty() const { return count == 0; }
        const String& operator[](size_t index) const;

        // Total entries ever added (monotonic); used to track what was sent.
        unsigned long total() const { return totalAdded; }
        unsigned long firstSequence() const { return totalAdded - count; }

        class const_iterator
        {
            public:
                const_iterator(const LogBuffer* buffer, size_t index) : buffer(buffer), index(index) {}
                const String& operator*() const { return (*buffer)[index]; }
                const_iterator& operator++() { ++index; return *this; }
                bool operator!=(const const_iterator& other) const { return index != other.index; }

            private:
                const LogBuffer* buffer;
                size_t index;
        };

        const_iterator begin() const { return const_iterator(this, 0); }
        const_iterator end() const { return const_iterator(this, count); }

    private:
        String entries[CAPACITY];
        size_t start = 0;
        size_t count = 0;
        unsigned long totalAdded = 0;
};

class Logger
{
    private:
        LogBuffer buffer;
        bool debugEnabled = false;

        void log(const char* level, const String& message);

    public:
        // Debug lines are dropped unless explicitly enabled: verbose
        // per-sample logging blocks the main loop (Serial) and floods the
        // websocket, which drops async connections.
        void setDebugEnabled(bool enabled) { this->debugEnabled = enabled; }

        void info(const String& message);
        void warning(const String& message);
        void error(const String& message);
        void debug(const String& message);
        const LogBuffer& getBuffer() const;
        size_t size() const;
};

#endif
