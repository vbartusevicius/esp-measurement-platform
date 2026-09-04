#include "Logger.h"
#include "TimeHelper.h"

void LogBuffer::add(const String& entry)
{
    if (count < CAPACITY) {
        entries[(start + count) % CAPACITY] = entry;
        count++;
    } else {
        entries[start] = entry;
        start = (start + 1) % CAPACITY;
    }
    totalAdded++;
}

const String& LogBuffer::operator[](size_t index) const
{
    return entries[(start + index) % CAPACITY];
}

void Logger::log(const char* level, const String& message)
{
    char timestamp[24];
    TimeHelper::getTimestamp(timestamp);

    String entry = String(timestamp) + " [" + level + "] " + message;

    Serial.println(entry);
    this->buffer.add(entry);
}

void Logger::info(const String& message)
{
    this->log("INFO", message);
}

void Logger::warning(const String& message)
{
    this->log("WARN", message);
}

void Logger::error(const String& message)
{
    this->log("ERROR", message);
}

void Logger::debug(const String& message)
{
    if (!this->debugEnabled) return;
    this->log("DEBUG", message);
}

const LogBuffer& Logger::getBuffer() const
{
    return this->buffer;
}

size_t Logger::size() const
{
    return this->buffer.size();
}
