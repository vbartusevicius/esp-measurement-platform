#ifndef STATUS_JSON_H
#define STATUS_JSON_H

#include <ArduinoJson.h>

class DeviceMonitor;
class IPlugin;
class Logger;
class Storage;

// Builds the live-status document sent by GET /api/v1/status and the
// WebSocket "stats_update" event, and the GET /api/v1/chart history.
namespace StatusJson
{
    struct Sources {
        const IPlugin* plugin;
        const Logger* logger;
        const DeviceMonitor* monitor;
        const Storage* storage;
        bool mqttConnected;
    };

    void write(JsonDocument& doc, const Sources& sources);
    void writeChart(JsonDocument& doc, const IPlugin* plugin);
}

#endif
