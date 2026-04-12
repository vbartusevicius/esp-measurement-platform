#include "WebApi.h"
#include "Parameter.h"
#include "ChipId.h"
#include "TimeHelper.h"
#include <ESP8266WiFi.h>

WebApi::WebApi(Storage* storage, Logger* logger, IPlugin* plugin, PluginRegistry* registry, ResetCallback resetCallback)
    : server(80), ws("/ws") {
    this->storage = storage;
    this->logger = logger;
    this->activePlugin = plugin;
    this->registry = registry;
    this->resetCallback = resetCallback;
    this->lastLogCount = 0;
}

void WebApi::begin() {
    if (!LittleFS.begin()) {
        this->logger->error("Failed to mount LittleFS");
        return;
    }

    this->setupWebSocket();
    this->setupApiEndpoints();
    this->setupStaticFiles();

    server.begin();
    this->logger->info("Web server started");
}

void WebApi::setupStaticFiles() {
    server.serveStatic("/", LittleFS, "/").setDefaultFile("index.html");

    server.onNotFound([this](AsyncWebServerRequest *request) {
        this->logger->warning("Not found: " + request->url());
        request->send(404, "text/plain", "Not found");
    });
}

void WebApi::setupApiEndpoints() {
    // GET /api/v1/plugins - list available plugins
    server.on("/api/v1/plugins", HTTP_GET, [this](AsyncWebServerRequest *request) {
        AsyncResponseStream *response = request->beginResponseStream("application/json");
        JsonDocument doc;
        JsonArray arr = doc["plugins"].to<JsonArray>();

        for (auto* p : this->registry->getAll()) {
            JsonObject obj = arr.add<JsonObject>();
            obj["id"] = p->getId();
            obj["name"] = p->getName();
            obj["active"] = (p == this->activePlugin);
        }

        serializeJson(doc, *response);
        request->send(response);
    });

    // GET /api/v1/config - returns core + plugin config + parameter definitions
    server.on("/api/v1/config", HTTP_GET, [this](AsyncWebServerRequest *request) {
        AsyncResponseStream *response = request->beginResponseStream("application/json");
        JsonDocument doc;

        // Core values
        doc["active_plugin"] = this->activePlugin->getId();
        doc["chip_id"] = ChipId::get();
        doc["mqtt_host"] = this->storage->getParameter(Parameter::MQTT_HOST, "");
        doc["mqtt_port"] = this->storage->getParameter(Parameter::MQTT_PORT, "1883");
        doc["mqtt_user"] = this->storage->getParameter(Parameter::MQTT_USER, "");
        doc["mqtt_pass"] = this->storage->getParameter(Parameter::MQTT_PASS, "");
        doc["mqtt_device"] = this->storage->getParameter(Parameter::MQTT_DEVICE, "");
        doc["mqtt_topic"] = this->storage->getParameter(Parameter::MQTT_TOPIC, "");

        // Plugin parameter values and definitions
        std::vector<ParameterDef> defs;
        this->activePlugin->getParameterDefs(defs);
        JsonArray paramDefs = doc["plugin_params"].to<JsonArray>();

        for (auto& def : defs) {
            JsonObject obj = paramDefs.add<JsonObject>();
            obj["key"] = def.key;
            obj["label"] = def.label;
            obj["default"] = def.defaultValue;
            obj["type"] = def.type == ParameterDef::NUMBER ? "number" :
                          def.type == ParameterDef::PASSWORD ? "password" : "text";
            obj["required"] = def.required;
            obj["value"] = this->storage->getParameter(def.key, def.defaultValue);
        }

        serializeJson(doc, *response);
        request->send(response);
    });

    // POST /api/v1/config - save all parameters
    server.on("/api/v1/config", HTTP_POST, [](AsyncWebServerRequest *request) {},
    nullptr,
    [this](AsyncWebServerRequest *request, uint8_t *data, size_t len, size_t index, size_t total) {
        if (index == 0) {
            request->_tempObject = malloc(total + 1);
        }
        memcpy((uint8_t*)request->_tempObject + index, data, len);

        if (index + len == total) {
            char* jsonData = (char*)request->_tempObject;
            jsonData[total] = '\0';

            JsonDocument jsonDoc;
            DeserializationError error = deserializeJson(jsonDoc, jsonData);

            if (!error) {
                JsonObject obj = jsonDoc.as<JsonObject>();
                for (JsonPair kv : obj) {
                    String key = kv.key().c_str();
                    String value = kv.value().as<String>();
                    this->storage->saveParameter(key.c_str(), value);
                }
                this->logger->info("Configuration saved");
                request->send(200, "application/json", "{\"status\":\"ok\"}");
            } else {
                this->logger->error("Failed to parse config JSON");
                request->send(400, "application/json", "{\"status\":\"error\",\"message\":\"Invalid JSON\"}");
            }

            free(request->_tempObject);
        }
    });

    // GET /api/v1/status
    server.on("/api/v1/status", HTTP_GET, [this](AsyncWebServerRequest *request) {
        AsyncResponseStream *response = request->beginResponseStream("application/json");
        JsonDocument doc;

        doc["chip_id"] = ChipId::get();
        doc["active_plugin"] = this->activePlugin->getId();
        doc["active_plugin_name"] = this->activePlugin->getName();
        doc["wifi_network"] = WiFi.SSID();
        doc["wifi_signal"] = String(WiFi.RSSI());
        doc["ip_address"] = WiFi.localIP().toString();
        doc["free_heap"] = ESP.getFreeHeap();

        char uptimeBuf[32];
        TimeHelper::getUptime(uptimeBuf);
        doc["uptime"] = uptimeBuf;

        // Plugin-specific stats
        std::vector<StatEntry> entries;
        this->activePlugin->getStats(entries);
        JsonArray statsArr = doc["stats"].to<JsonArray>();
        for (auto& e : entries) {
            JsonObject obj = statsArr.add<JsonObject>();
            obj["label"] = e.label;
            obj["value"] = e.value;
            obj["numeric"] = e.numericValue;
            obj["render"] = e.render == StatEntry::PROGRESS ? "progress" : "text";
            obj["primary"] = e.primary;
        }

        serializeJson(doc, *response);
        request->send(response);
    });

    // POST /api/v1/restart
    server.on("/api/v1/restart", HTTP_POST, [](AsyncWebServerRequest *request) {
        request->send(200, "application/json", "{\"status\":\"restarting\"}");
        delay(500);
        ESP.restart();
    });

    // POST /api/v1/reset
    server.on("/api/v1/reset", HTTP_POST, [this](AsyncWebServerRequest *request) {
        request->send(200, "application/json", "{\"status\":\"resetting\"}");
        this->resetCallback();
    });
}

void WebApi::setupWebSocket() {
    ws.onEvent([this](AsyncWebSocket *server, AsyncWebSocketClient *client,
                AwsEventType type, void *arg, uint8_t *data, size_t len) {
        switch (type) {
            case WS_EVT_CONNECT:
                this->logger->info("WebSocket client connected: " + String(client->id()));
                break;
            case WS_EVT_DISCONNECT:
                this->logger->info("WebSocket client disconnected");
                break;
            case WS_EVT_DATA:
                this->handleWebSocketMessage(client, arg, data, len);
                break;
            case WS_EVT_PONG:
            case WS_EVT_ERROR:
                break;
        }
    });

    server.addHandler(&ws);
}

void WebApi::handleWebSocketMessage(AsyncWebSocketClient* client, void* arg, uint8_t* data, size_t len) {
    AwsFrameInfo *info = (AwsFrameInfo*)arg;
    if (info->final && info->index == 0 && info->len == len && info->opcode == WS_TEXT) {
        char* cstr = new char[len + 1];
        memcpy(cstr, data, len);
        cstr[len] = 0;

        JsonDocument doc;
        DeserializationError error = deserializeJson(doc, cstr);
        delete[] cstr;

        if (error) return;

        if (doc["event"] == "request_status") {
            this->broadcastStats();
        } else if (doc["event"] == "request_logs") {
            this->sendLogHistory(client);
        }
    }
}

void WebApi::broadcastStats() {
    if (ws.count() == 0) return;

    JsonDocument doc;
    doc["event"] = "stats_update";
    doc["wifi_network"] = WiFi.SSID();
    doc["wifi_signal"] = String(WiFi.RSSI());
    doc["ip_address"] = WiFi.localIP().toString();
    doc["free_heap"] = ESP.getFreeHeap();
    doc["mqtt_connected"] = this->mqttConnected;

    char uptimeBuf[32];
    TimeHelper::getUptime(uptimeBuf);
    doc["uptime"] = uptimeBuf;

    // Plugin-specific stats as structured array
    std::vector<StatEntry> entries;
    this->activePlugin->getStats(entries);
    JsonArray statsArr = doc["stats"].to<JsonArray>();
    for (auto& e : entries) {
        JsonObject obj = statsArr.add<JsonObject>();
        obj["label"] = e.label;
        obj["value"] = e.value;
        obj["numeric"] = e.numericValue;
        obj["render"] = e.render == StatEntry::PROGRESS ? "progress" : "text";
        obj["primary"] = e.primary;
    }

    String message;
    serializeJson(doc, message);
    ws.textAll(message);
}

void WebApi::broadcastLogs() {
    if (ws.count() == 0) return;

    const auto& logs = this->logger->getBuffer();
    if (logs.size() <= lastLogCount) return;

    JsonDocument logsDoc;
    logsDoc["event"] = "log_batch";
    JsonArray arr = logsDoc["messages"].to<JsonArray>();

    for (size_t i = lastLogCount; i < logs.size(); i++) {
        arr.add(logs[i]);
    }
    lastLogCount = logs.size();

    String message;
    serializeJson(logsDoc, message);
    ws.textAll(message);
}

void WebApi::sendLogHistory(AsyncWebSocketClient* client) {
    const auto& logs = this->logger->getBuffer();
    if (logs.empty()) return;

    JsonDocument logsDoc;
    logsDoc["event"] = "log_batch";
    JsonArray arr = logsDoc["messages"].to<JsonArray>();

    for (auto& entry : logs) {
        arr.add(entry);
    }

    String response;
    serializeJson(logsDoc, response);
    client->text(response);
}

void WebApi::run(bool mqttConnected) {
    this->mqttConnected = mqttConnected;
    ws.cleanupClients();
    broadcastStats();
    broadcastLogs();
}
