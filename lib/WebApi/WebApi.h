#ifndef WEB_API_H
#define WEB_API_H

#ifdef ESP8266WEBSERVER_H
#define WEBSERVER_H
#endif

#include <ESPAsyncWebServer.h>
#include <AsyncWebSocket.h>
#if defined(ESP32)
#include <AsyncTCP.h>
#else
#include <ESPAsyncTCP.h>
#endif
#include <ArduinoJson.h>
#include "Logger.h"
#include "Storage.h"
#include "IPlugin.h"
#include "PluginRegistry.h"
#include "DeviceMonitor.h"
#include "RelayOutput.h"
#include "Display.h"

typedef void (*ResetCallback)();
typedef void (*ActionCallback)();

class WebApi {
    private:
        AsyncWebServer server;
        AsyncWebSocket ws;
        Storage* storage;
        Logger* logger;
        IPlugin* activePlugin;
        PluginRegistry* registry;
        ResetCallback resetCallback;
        unsigned long lastLogSequence;
        bool mqttConnected;
        unsigned long restartAt = 0;
        static constexpr size_t MAX_CONFIG_BODY_SIZE = 2048;
        static constexpr size_t MAX_LOG_LINES_PER_MESSAGE = 15;

        DeviceMonitor* monitor = nullptr;
        Display* display = nullptr;
        ActionCallback pagePress = nullptr;

        // Requests from the async web task, applied on the main loop by processActions()
        volatile int pendingRelay = -1;
        volatile bool pendingPage = false;
        volatile bool pendingDismiss = false;
        volatile bool pendingLimitsReload = false;

    public:
        WebApi(Storage* storage, Logger* logger, IPlugin* plugin, PluginRegistry* registry, ResetCallback resetCallback);

        void begin();
        void run(bool mqttConnected);
        size_t websocketClients() { return ws.count(); }
        void setDevice(DeviceMonitor* monitor, Display* display, ActionCallback pagePress);
        void processActions();

    private:
        void setupStaticFiles();
        void setupApiEndpoints();
        void setupWebSocket();

        void setupUploadEndpoint();
        void handleUpload(AsyncWebServerRequest* request, const String& filename,
                          size_t index, uint8_t* data, size_t len, bool final);

        void handleWebSocketMessage(AsyncWebSocketClient* client, void* arg, uint8_t* data, size_t len);
        void fillStatus(JsonDocument& doc);
        void broadcastStats();
        void broadcastLogs();
        void sendLogHistory(AsyncWebSocketClient* client);
};

#endif
