#ifndef TIME_HELPER_H
#define TIME_HELPER_H

#include <Arduino.h>

class TimeHelper
{
    public:
        static void getUptime(char* buffer);
        static void getTimestamp(char* buffer);

    private:
        static const unsigned long MSECS_PER_SEC = 1000;
        static const unsigned long SECS_PER_MIN = 60;
        static const unsigned long SECS_PER_HOUR = 3600;
        static const unsigned long SECS_PER_DAY = 86400;
};

#endif
