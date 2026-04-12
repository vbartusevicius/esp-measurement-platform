#ifndef LOGGER_H
#define LOGGER_H

#include <Arduino.h>
#include <vector>

class Logger
{
    private:
        static const size_t MAX_ENTRIES = 50;
        std::vector<String> buffer;

        void log(const char* level, const String& message);

    public:
        void info(const String& message);
        void warning(const String& message);
        void error(const String& message);
        void debug(const String& message);
        const std::vector<String>& getBuffer() const;
        size_t size() const;
};

#endif
