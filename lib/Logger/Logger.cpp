#include "Logger.h"
#include "TimeHelper.h"

void Logger::log(const char* level, const String& message)
{
    char timestamp[24];
    TimeHelper::getTimestamp(timestamp);

    String entry = String(timestamp) + " [" + level + "] " + message;

    Serial.println(entry);

    if (this->buffer.size() >= MAX_ENTRIES) {
        this->buffer.erase(this->buffer.begin());
    }
    this->buffer.push_back(entry);
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
    this->log("DEBUG", message);
}

const std::vector<String>& Logger::getBuffer() const
{
    return this->buffer;
}

size_t Logger::size() const
{
    return this->buffer.size();
}
