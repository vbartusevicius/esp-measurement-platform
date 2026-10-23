#ifndef OTA_UPDATES_H
#define OTA_UPDATES_H

class Logger;

// espota (Arduino IDE / `pio run -t upload` over the network) updates.
namespace OtaUpdates
{
    void begin(Logger* logger);
    void handle();
}

#endif
