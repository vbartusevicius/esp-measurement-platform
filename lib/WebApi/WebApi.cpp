#include "WebApi.h"
#include "Parameter.h"
#include "ChipId.h"
#include "TimeHelper.h"
#include "Version.h"
#include <ESP8266WiFi.h>
#include <Updater.h>

extern "C" uint32_t _FS_start;
extern "C" uint32_t _FS_end;

static float rounded(float v) { return (float)(int)(v * 100 + 0.5f) / 100.0f; }

WebApi::WebApi(Storage* storage, Logger* logger, IPlugin* plugin, PluginRegistry* registry, ResetCallback resetCallback)
    : server(80), ws("/ws") {
    this->storage = storage;
    this->logger = logger;
    this->activePlugin = plugin;
    this->registry = registry;
    this->resetCallback = resetCallback;
    this->lastLogSequence = 0;
}

void WebApi::begin() {
    if (!LittleFS.begin()) {
        this->logger->error("Failed to mount LittleFS");
        return;
    }

    this->setupWebSocket();
    this->setupApiEndpoints();
    this->setupUploadEndpoint();
    this->setupStaticFiles();

    server.begin();
    this->logger->info("Web server started");
}

void WebApi::setupStaticFiles() {
    server.serveStatic("/", LittleFS, "/")
        .setDefaultFile("index.html");

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

        // Find which plugin to get parameters for
        IPlugin* pluginToInspect = this->activePlugin;
        if (request->hasParam("plugin")) {
            String pId = request->getParam("plugin")->value();
            IPlugin* reqP = this->registry->get(pId.c_str());
            if (reqP) pluginToInspect = reqP;
        }

        // Core values
        doc["active_plugin"] = this->activePlugin ? this->activePlugin->getId() : "";
        doc["chip_id"] = ChipId::get();
        doc["device_name"] = this->storage->getParameter(Parameter::DEVICE_NAME, "");
        doc["mqtt_host"] = this->storage->getParameter(Parameter::MQTT_HOST, "");
        doc["mqtt_port"] = this->storage->getParameter(Parameter::MQTT_PORT, "1883");
        doc["mqtt_user"] = this->storage->getParameter(Parameter::MQTT_USER, "");
        doc["mqtt_pass"] = this->storage->getParameter(Parameter::MQTT_PASS, "");
        doc["mqtt_device"] = this->storage->getParameter(Parameter::MQTT_DEVICE, "");
        doc["mqtt_topic"] = this->storage->getParameter(Parameter::MQTT_TOPIC, "");
        doc["firmware_version"] = FW_VERSION;

        // Plugin parameter values and definitions
        std::vector<ParameterDef> defs;
        if (pluginToInspect) {
            pluginToInspect->getParameterDefs(defs);
        }
        
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
        if (total > MAX_CONFIG_BODY_SIZE) {
            if (index + len == total) {
                request->send(413, "application/json", "{\"status\":\"error\",\"message\":\"Payload too large\"}");
            }
            return;
        }

        if (index == 0) {
            request->_tempObject = malloc(total + 1);
            if (!request->_tempObject) {
                request->send(500, "application/json", "{\"status\":\"error\",\"message\":\"Out of memory\"}");
                return;
            }
        }

        if (!request->_tempObject) return;
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

            // _tempObject is freed in the AsyncWebServerRequest destructor
        }
    });

    // GET /api/v1/status
    server.on("/api/v1/status", HTTP_GET, [this](AsyncWebServerRequest *request) {
        AsyncResponseStream *response = request->beginResponseStream("application/json");
        JsonDocument doc;

        doc["chip_id"] = ChipId::get();
        doc["active_plugin"] = this->activePlugin ? this->activePlugin->getId() : "";
        doc["active_plugin_name"] = this->activePlugin ? this->activePlugin->getName() : "None";
        doc["wifi_network"] = WiFi.SSID();
        doc["wifi_signal"] = String(WiFi.RSSI());
        doc["ip_address"] = WiFi.localIP().toString();
        doc["free_heap"] = ESP.getFreeHeap();
        doc["firmware_version"] = FW_VERSION;

        char uptimeBuf[32];
        TimeHelper::getUptime(uptimeBuf);
        doc["uptime"] = uptimeBuf;

        // Plugin-specific stats
        std::vector<StatEntry> entries;
        if (this->activePlugin) {
            this->activePlugin->getStats(entries);
        }
        
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

    // GET /api/v1/chart - history chart data (plugins that support it)
    server.on("/api/v1/chart", HTTP_GET, [this](AsyncWebServerRequest *request) {
        AsyncResponseStream *response = request->beginResponseStream("application/json");
        JsonDocument doc;

        std::vector<float> points;
        int spanSeconds = 0;
        if (this->activePlugin && this->activePlugin->getChartData(points, spanSeconds) && !points.empty()) {
            JsonArray arr = doc["points"].to<JsonArray>();
            for (float v : points) arr.add(rounded(v));
            doc["span_seconds"] = spanSeconds;
            doc["unit"] = "\xC2\xB5Sv/h";  // only the radiation plugin supports charts today
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

void WebApi::setupUploadEndpoint() {
    server.on("/api/v1/upload", HTTP_POST,
        [this](AsyncWebServerRequest *request) {
            const bool ok = !Update.hasError();
            AsyncWebServerResponse *response = request->beginResponse(
                ok ? 200 : 500, "application/json",
                ok ? "{\"status\":\"ok\",\"message\":\"Update applied, restarting\"}"
                   : "{\"status\":\"error\",\"message\":\"Update failed\"}");
            response->addHeader("Connection", "close");
            request->send(response);

            if (ok) {
                this->logger->info("Upload complete, restarting");
                this->restartAt = millis() + 500;   // let the response flush first
            }
        },
        [this](AsyncWebServerRequest *request, const String& filename, size_t index,
               uint8_t *data, size_t len, bool final) {
            this->handleUpload(request, filename, index, data, len, final);
        });
}

void WebApi::handleUpload(AsyncWebServerRequest* request, const String& filename,
                          size_t index, uint8_t* data, size_t len, bool final) {
    if (index == 0) {
        const bool filesystem = request->hasParam("target", true)
            ? request->getParam("target", true)->value() == "filesystem"
            : request->hasParam("target") && request->getParam("target")->value() == "filesystem";

        this->logger->info(String("Upload started: ") + filename +
                           (filesystem ? " (filesystem)" : " (firmware)") +
                           " free=" + String(ESP.getFreeHeap()) +
                           " maxBlock=" + String(ESP.getMaxFreeBlockSize()));

        // Free the websocket buffers: Update.begin() needs 4 KB contiguous.
        ws.closeAll();
        ws.enable(false);

        size_t maxSize;
        int command;
        if (filesystem) {
            maxSize = (size_t)&_FS_end - (size_t)&_FS_start;
            command = U_FS;
            LittleFS.end();   // must not be mounted while it is overwritten
        } else {
            maxSize = (ESP.getFreeSketchSpace() - 0x1000) & 0xFFFFF000;
            command = U_FLASH;
        }

        Update.runAsync(true);
        if (!Update.begin(maxSize, command)) {
            this->logger->error("Update.begin failed: " + String(Update.getErrorString()));
        }
    }

    if (Update.hasError()) return;

    if (len && Update.write(data, len) != len) {
        this->logger->error("Upload write failed: " + String(Update.getErrorString()));
        return;
    }

    if (final) {
        if (Update.end(true)) {
            this->logger->info("Upload flashed " + String(index + len) + " bytes");
        } else {
            this->logger->error("Update.end failed: " + String(Update.getErrorString()));
        }
    }
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
    // Skip the update if a client's send queue is still backed up: piling
    // messages onto a slow client drops frames and starves async TCP.
    if (!ws.availableForWriteAll()) return;

    JsonDocument doc;
    doc["event"] = "stats_update";
    doc["wifi_network"] = WiFi.SSID();
    doc["wifi_signal"] = String(WiFi.RSSI());
    doc["ip_address"] = WiFi.localIP().toString();
    doc["free_heap"] = ESP.getFreeHeap();
    doc["mqtt_connected"] = this->mqttConnected;
    doc["firmware_version"] = FW_VERSION;

    char uptimeBuf[32];
    TimeHelper::getUptime(uptimeBuf);
    doc["uptime"] = uptimeBuf;

    // Plugin-specific stats as structured array
    std::vector<StatEntry> entries;
    if (this->activePlugin) {
        this->activePlugin->getStats(entries);
    }
    
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
    if (!ws.availableForWriteAll()) return;

    const auto& logs = this->logger->getBuffer();
    unsigned long total = logs.total();

    // Nothing new since the last broadcast (sequence numbers survive buffer wrap)
    if (total <= this->lastLogSequence) return;

    JsonDocument logsDoc;
    logsDoc["event"] = "log_batch";
    JsonArray arr = logsDoc["messages"].to<JsonArray>();

    unsigned long firstSeq = logs.firstSequence();
    size_t startIdx = this->lastLogSequence > firstSeq ? (size_t)(this->lastLogSequence - firstSeq) : 0;
    if (logs.size() - startIdx > MAX_LOG_LINES_PER_MESSAGE) {
        startIdx = logs.size() - MAX_LOG_LINES_PER_MESSAGE;
    }
    for (size_t i = startIdx; i < logs.size(); i++) {
        arr.add(logs[i]);
    }
    this->lastLogSequence = total;

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

    // Only the most recent lines: the whole buffer serialises to several KB,
    // and doc + String + the async copy would peak at ~3x that on a ~40 KB heap.
    size_t startIdx = logs.size() > MAX_LOG_LINES_PER_MESSAGE
        ? logs.size() - MAX_LOG_LINES_PER_MESSAGE : 0;
    for (size_t i = startIdx; i < logs.size(); i++) {
        arr.add(logs[i]);
    }

    String response;
    serializeJson(logsDoc, response);
    client->text(response);
}

void WebApi::run(bool mqttConnected) {
    if (this->restartAt && (long)(millis() - this->restartAt) >= 0) {
        ESP.restart();
    }

    this->mqttConnected = mqttConnected;
    ws.cleanupClients();
    broadcastStats();
    broadcastLogs();
}
