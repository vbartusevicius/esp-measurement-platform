#ifndef WEB_API_H
#define WEB_API_H

#ifdef ESP8266WEBSERVER_H
#define WEBSERVER_H
#endif

#include <ESPAsyncWebServer.h>
#include <AsyncWebSocket.h>
#include <ESPAsyncTCP.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include "Logger.h"
#include "Storage.h"
#include "IPlugin.h"
#include "PluginRegistry.h"

typedef void (*ResetCallback)();

class ReleaseUpdater;

class WebApi {
    private:
        AsyncWebServer server;
        AsyncWebSocket ws;
        Storage* storage;
        Logger* logger;
        IPlugin* activePlugin;
        PluginRegistry* registry;
        ResetCallback resetCallback;
        ReleaseUpdater* releaseUpdater = nullptr;
        unsigned long lastLogSequence;
        bool mqttConnected;
        static constexpr size_t MAX_CONFIG_BODY_SIZE = 2048;
        static constexpr size_t MAX_LOG_LINES_PER_MESSAGE = 15;

    public:
        WebApi(Storage* storage, Logger* logger, IPlugin* plugin, PluginRegistry* registry, ResetCallback resetCallback, ReleaseUpdater* releaseUpdater = nullptr);

        void begin();
        void run(bool mqttConnected);
        size_t websocketClients() { return ws.count(); }

    private:
        void setupStaticFiles();
        void setupApiEndpoints();
        void setupWebSocket();

        void handleWebSocketMessage(AsyncWebSocketClient* client, void* arg, uint8_t* data, size_t len);
        void broadcastStats();
        void broadcastLogs();
        void sendLogHistory(AsyncWebSocketClient* client);
};

#endif
