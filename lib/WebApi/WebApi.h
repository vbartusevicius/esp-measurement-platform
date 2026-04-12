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
#include <vector>
#include "Logger.h"
#include "Storage.h"
#include "IPlugin.h"
#include "PluginRegistry.h"

typedef void (*ResetCallback)();

class WebApi {
    private:
        AsyncWebServer server;
        AsyncWebSocket ws;
        Storage* storage;
        Logger* logger;
        IPlugin* activePlugin;
        PluginRegistry* registry;
        ResetCallback resetCallback;
        size_t lastLogCount;
        bool mqttConnected;

    public:
        WebApi(Storage* storage, Logger* logger, IPlugin* plugin, PluginRegistry* registry, ResetCallback resetCallback);

        void begin();
        void run(bool mqttConnected);

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
