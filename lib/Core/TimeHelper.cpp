#include "TimeHelper.h"

void TimeHelper::getUptime(char* buffer)
{
    const unsigned long msecs = millis();
    const unsigned long secs = msecs / TimeHelper::MSECS_PER_SEC;

    const unsigned long Seconds = secs % TimeHelper::SECS_PER_MIN;
    const unsigned long Minutes = (secs / TimeHelper::SECS_PER_MIN) % TimeHelper::SECS_PER_MIN;
    const unsigned long Hours = (secs % TimeHelper::SECS_PER_DAY) / TimeHelper::SECS_PER_HOUR;
    const unsigned long Days = (secs / TimeHelper::SECS_PER_DAY);

    sprintf(buffer, "%02dd %02d:%02d:%02d", (int)Days, (int)Hours, (int)Minutes, (int)Seconds);
}

void TimeHelper::getTimestamp(char* buffer)
{
    const unsigned long msecs = millis();
    const unsigned long secs = msecs / TimeHelper::MSECS_PER_SEC;

    const unsigned long MilliSeconds = msecs % TimeHelper::MSECS_PER_SEC;
    const unsigned long Seconds = secs % TimeHelper::SECS_PER_MIN;
    const unsigned long Minutes = (secs / TimeHelper::SECS_PER_MIN) % TimeHelper::SECS_PER_MIN;
    const unsigned long Hours = (secs % TimeHelper::SECS_PER_DAY) / TimeHelper::SECS_PER_HOUR;

    sprintf(buffer, "%02d:%02d:%02d.%03d", (int)Hours, (int)Minutes, (int)Seconds, (int)MilliSeconds);
}
