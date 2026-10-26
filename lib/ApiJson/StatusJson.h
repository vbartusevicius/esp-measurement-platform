#ifndef STATUS_JSON_H
#define STATUS_JSON_H

#include <ArduinoJson.h>

class DeviceMonitor;
class Logger;
class SensorHub;
class Storage;

// Builds the live-status document sent by GET /api/v1/status and the
// WebSocket "stats_update" event, and the GET /api/v1/chart history.
namespace StatusJson
{
    struct Sources {
        const SensorHub* hub;
        const Logger* logger;
        const DeviceMonitor* monitor;
        const Storage* storage;
        bool mqttConnected;
    };

    // Device state, then "sensors": [{id, name, configured, screen, stats, limits}] in display order.
    void write(JsonDocument& doc, const Sources& sources);
    void writeChart(JsonDocument& doc, const SensorHub& hub, int sensor);
}

#endif
