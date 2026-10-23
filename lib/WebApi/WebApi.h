#ifndef WEB_API_H
#define WEB_API_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESPAsyncWebServer.h>

class DeviceMonitor;
class IPlugin;
class Logger;
class PluginRegistry;
class Storage;

typedef void (*ResetCallback)();

// HTTP routes, WebSocket and firmware upload. JSON documents are built by
// ConfigJson / StatusJson; this class only moves them over the wire.
class WebApi {
    private:
        AsyncWebServer server;
        AsyncWebSocket ws;
        Storage* storage;
        Logger* logger;
        IPlugin* activePlugin;
        PluginRegistry* registry;
        DeviceMonitor* monitor;
        ResetCallback resetCallback;
        unsigned long lastLogSequence = 0;
        bool mqttConnected = false;
        unsigned long restartAt = 0;
        const char* uploadRejected = nullptr;   // why the current upload was refused before flashing
        static constexpr size_t MAX_CONFIG_BODY_SIZE = 2048;
        static constexpr size_t MAX_LOG_LINES_PER_MESSAGE = 15;

        // Requests from the async web task, applied on the main loop by processActions()
        volatile int pendingRelay = -1;
        volatile bool pendingAlertAck = false;
        volatile bool pendingLimitsReload = false;

    public:
        WebApi(Storage* storage, Logger* logger, IPlugin* plugin, PluginRegistry* registry,
               DeviceMonitor* monitor, ResetCallback resetCallback);

        void begin();
        void run(bool mqttConnected);
        void processActions();

    private:
        void setupStaticFiles();
        void setupApiEndpoints();
        void setupWebSocket();
        void setupUploadEndpoint();
        void handleConfigBody(AsyncWebServerRequest* request, uint8_t* data, size_t len, size_t index, size_t total);
        void handleRelay(AsyncWebServerRequest* request);
        void handleUpload(AsyncWebServerRequest* request, const String& filename,
                          size_t index, uint8_t* data, size_t len, bool final);

        void handleWebSocketMessage(AsyncWebSocketClient* client, void* arg, uint8_t* data, size_t len);
        void writeStatus(JsonDocument& doc);
        void broadcastStats();
        void broadcastLogs();
        void sendLogHistory(AsyncWebSocketClient* client);
};

#endif
