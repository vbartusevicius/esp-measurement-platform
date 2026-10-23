#include "WebApi.h"
#include "ConfigJson.h"
#include "DeviceMonitor.h"
#include "IPlugin.h"
#include "Logger.h"
#include "PluginRegistry.h"
#include "RelayOutput.h"
#include "StatusJson.h"
#include "Storage.h"
#include "WebAssets.h"
#if defined(ESP32)
#include <Update.h>
static String updateError() { return String(Update.errorString()); }
#else
#include <Updater.h>
static String updateError() { return String(Update.getErrorString()); }
#endif

static void sendJson(AsyncWebServerRequest* request, JsonDocument& doc)
{
    AsyncResponseStream* response = request->beginResponseStream("application/json");
    serializeJson(doc, *response);
    request->send(response);
}

static void sendResult(AsyncWebServerRequest* request, int code, const char* message = nullptr)
{
    JsonDocument doc;
    doc["status"] = code < 400 ? "ok" : "error";
    if (message) doc["message"] = message;
    String body;
    serializeJson(doc, body);
    request->send(code, "application/json", body);
}

WebApi::WebApi(Storage* storage, Logger* logger, IPlugin* plugin, PluginRegistry* registry,
               DeviceMonitor* monitor, ResetCallback resetCallback)
    : server(80), ws("/ws"), storage(storage), logger(logger), activePlugin(plugin),
      registry(registry), monitor(monitor), resetCallback(resetCallback)
{
}

void WebApi::begin()
{
    this->setupWebSocket();
    this->setupApiEndpoints();
    this->setupUploadEndpoint();
    this->setupStaticFiles();

    server.begin();
    this->logger->info("Web server started");
}

void WebApi::setupStaticFiles()
{
    // The web UI is compiled into the firmware (tools/embed_web.py): gzipped,
    // with one ETag per build so browsers revalidate instead of re-downloading.
    for (size_t i = 0; i < WEB_ASSET_COUNT; i++) {
        const WebAsset* asset = &WEB_ASSETS[i];
        auto handler = [asset](AsyncWebServerRequest *request) {
            if (request->hasHeader("If-None-Match") && request->header("If-None-Match") == WEB_ASSETS_ETAG) {
                request->send(304);
                return;
            }
#if defined(ESP32)
            AsyncWebServerResponse *response = request->beginResponse(200, asset->mime, asset->gzip, asset->length);
#else
            AsyncWebServerResponse *response = request->beginResponse_P(200, asset->mime, asset->gzip, asset->length);
#endif
            response->addHeader("Content-Encoding", "gzip");
            response->addHeader("ETag", WEB_ASSETS_ETAG);
            response->addHeader("Cache-Control", "no-cache");
            request->send(response);
        };
        server.on(asset->path, HTTP_GET, handler);
        if (strcmp(asset->path, "/index.html") == 0) server.on("/", HTTP_GET, handler);
    }

    server.onNotFound([this](AsyncWebServerRequest *request) {
        this->logger->warning("Not found: " + request->url());
        request->send(404, "text/plain", "Not found");
    });
}

void WebApi::setupApiEndpoints()
{
    server.on("/api/v1/plugins", HTTP_GET, [this](AsyncWebServerRequest *request) {
        JsonDocument doc;
        ConfigJson::writePlugins(doc, *this->registry, this->activePlugin);
        sendJson(request, doc);
    });

    // ?plugin=<id> lists that plugin's parameters (sensor dropdown before saving)
    server.on("/api/v1/config", HTTP_GET, [this](AsyncWebServerRequest *request) {
        IPlugin* inspected = this->activePlugin;
        if (request->hasParam("plugin")) {
            IPlugin* requested = this->registry->get(request->getParam("plugin")->value().c_str());
            if (requested) inspected = requested;
        }
        JsonDocument doc;
        ConfigJson::writeConfig(doc, *this->storage, this->activePlugin, inspected, this->monitor);
        sendJson(request, doc);
    });

    server.on("/api/v1/config", HTTP_POST, [](AsyncWebServerRequest *request) {}, nullptr,
        [this](AsyncWebServerRequest *request, uint8_t *data, size_t len, size_t index, size_t total) {
            this->handleConfigBody(request, data, len, index, total);
        });

    server.on("/api/v1/status", HTTP_GET, [this](AsyncWebServerRequest *request) {
        JsonDocument doc;
        this->writeStatus(doc);
        sendJson(request, doc);
    });

    server.on("/api/v1/chart", HTTP_GET, [this](AsyncWebServerRequest *request) {
        JsonDocument doc;
        StatusJson::writeChart(doc, this->activePlugin);
        sendJson(request, doc);
    });

    // POST /api/v1/relay?state=on|off - manual relay control
    server.on("/api/v1/relay", HTTP_POST, [this](AsyncWebServerRequest *request) {
        this->handleRelay(request);
    });

    // Same as the PAGE button while an alert is shown
    server.on("/api/v1/alert/ack", HTTP_POST, [this](AsyncWebServerRequest *request) {
        this->pendingAlertAck = true;
        sendResult(request, 200);
    });

    server.on("/api/v1/restart", HTTP_POST, [](AsyncWebServerRequest *request) {
        sendResult(request, 200, "Restarting");
        delay(500);
        ESP.restart();
    });

    server.on("/api/v1/reset", HTTP_POST, [this](AsyncWebServerRequest *request) {
        sendResult(request, 200, "Resetting");
        this->resetCallback();
    });
}

void WebApi::handleConfigBody(AsyncWebServerRequest* request, uint8_t* data, size_t len, size_t index, size_t total)
{
    if (total > MAX_CONFIG_BODY_SIZE) {
        if (index + len == total) sendResult(request, 413, "Payload too large");
        return;
    }
    if (index == 0) {
        request->_tempObject = malloc(total + 1);   // freed by the AsyncWebServerRequest destructor
        if (!request->_tempObject) {
            sendResult(request, 500, "Out of memory");
            return;
        }
    }
    if (!request->_tempObject) return;
    memcpy((uint8_t*)request->_tempObject + index, data, len);
    if (index + len != total) return;

    char* body = (char*)request->_tempObject;
    body[total] = '\0';
    JsonDocument doc;
    if (deserializeJson(doc, body)) {
        this->logger->error("Failed to parse config JSON");
        sendResult(request, 400, "Invalid JSON");
        return;
    }
    for (JsonPair kv : doc.as<JsonObject>()) {
        this->storage->saveParameter(kv.key().c_str(), kv.value().as<String>());
    }
    this->logger->info("Configuration saved");
    this->pendingLimitsReload = true;
    sendResult(request, 200);
}

void WebApi::handleRelay(AsyncWebServerRequest* request)
{
    if (!this->monitor || !this->monitor->relayAvailable()) {
        sendResult(request, 404, "No relay on this board");
        return;
    }
    if (this->monitor->limits().relayMode() != LimitMonitor::RelayMode::MANUAL) {
        sendResult(request, 409, "Relay follows the limit rule");
        return;
    }
    bool on = false;
    String state = request->hasParam("state") ? request->getParam("state")->value() : String();
    if (!RelayOutput::parseCommand(state.c_str(), on)) {
        sendResult(request, 400, "state must be on or off");
        return;
    }
    this->pendingRelay = on ? 1 : 0;
    sendResult(request, 200);
}

void WebApi::setupUploadEndpoint()
{
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
                          size_t index, uint8_t* data, size_t len, bool final)
{
    if (index == 0) {
#if defined(ESP32)
        const uint32_t maxBlock = ESP.getMaxAllocHeap();
#else
        const uint32_t maxBlock = ESP.getMaxFreeBlockSize();
#endif
        // The web UI is part of firmware.bin, so firmware is the only target.
        this->logger->info(String("Upload started: ") + filename +
                           " free=" + String(ESP.getFreeHeap()) +
                           " maxBlock=" + String(maxBlock));

        // Free the websocket buffers: Update.begin() needs 4 KB contiguous.
        ws.closeAll();
        ws.enable(false);

#if defined(ESP32)
        const size_t maxSize = UPDATE_SIZE_UNKNOWN;   // the target partition bounds the image
#else
        const size_t maxSize = (ESP.getFreeSketchSpace() - 0x1000) & 0xFFFFF000;
        Update.runAsync(true);
#endif
        if (!Update.begin(maxSize, U_FLASH)) {
            this->logger->error("Update.begin failed: " + updateError());
        }
    }

    if (Update.hasError()) return;

    if (len && Update.write(data, len) != len) {
        this->logger->error("Upload write failed: " + updateError());
        return;
    }

    if (final) {
        if (Update.end(true)) {
            this->logger->info("Upload flashed " + String(index + len) + " bytes");
        } else {
            this->logger->error("Update.end failed: " + updateError());
        }
    }
}

void WebApi::setupWebSocket()
{
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
            default:
                break;
        }
    });

    server.addHandler(&ws);
}

void WebApi::handleWebSocketMessage(AsyncWebSocketClient* client, void* arg, uint8_t* data, size_t len)
{
    AwsFrameInfo *info = (AwsFrameInfo*)arg;
    if (!info->final || info->index != 0 || info->len != len || info->opcode != WS_TEXT) return;

    JsonDocument doc;
    if (deserializeJson(doc, (const char*)data, len)) return;

    if (doc["event"] == "request_status") {
        this->broadcastStats();
    } else if (doc["event"] == "request_logs") {
        this->sendLogHistory(client);
    }
}

void WebApi::writeStatus(JsonDocument& doc)
{
    StatusJson::write(doc, {this->activePlugin, this->logger, this->monitor, this->storage, this->mqttConnected});
}

void WebApi::broadcastStats()
{
    // Skip the update if a client's send queue is still backed up: piling
    // messages onto a slow client drops frames and starves async TCP.
    if (ws.count() == 0 || !ws.availableForWriteAll()) return;

    JsonDocument doc;
    doc["event"] = "stats_update";
    this->writeStatus(doc);

    String message;
    serializeJson(doc, message);
    ws.textAll(message);
}

void WebApi::processActions()
{
    if (!this->monitor) return;
    if (this->pendingLimitsReload) {
        this->pendingLimitsReload = false;
        this->monitor->loadLimits();
    }
    int relay = this->pendingRelay;
    if (relay >= 0) {
        this->pendingRelay = -1;
        this->monitor->commandRelay(relay == 1, "WEB UI", millis());
    }
    if (this->pendingAlertAck) {
        this->pendingAlertAck = false;
        this->monitor->dismissAlert();
    }
}

void WebApi::broadcastLogs()
{
    if (ws.count() == 0 || !ws.availableForWriteAll()) return;

    const LogBuffer& logs = this->logger->getBuffer();
    unsigned long total = logs.total();

    // Nothing new since the last broadcast (sequence numbers survive buffer wrap)
    if (total <= this->lastLogSequence) return;

    JsonDocument doc;
    doc["event"] = "log_batch";
    JsonArray arr = doc["messages"].to<JsonArray>();

    unsigned long firstSeq = logs.firstSequence();
    size_t startIdx = this->lastLogSequence > firstSeq ? (size_t)(this->lastLogSequence - firstSeq) : 0;
    if (logs.size() - startIdx > MAX_LOG_LINES_PER_MESSAGE) {
        startIdx = logs.size() - MAX_LOG_LINES_PER_MESSAGE;
    }
    for (size_t i = startIdx; i < logs.size(); i++) arr.add(logs[i]);
    this->lastLogSequence = total;

    String message;
    serializeJson(doc, message);
    ws.textAll(message);
}

void WebApi::sendLogHistory(AsyncWebSocketClient* client)
{
    const LogBuffer& logs = this->logger->getBuffer();
    if (logs.empty()) return;

    JsonDocument doc;
    doc["event"] = "log_batch";
    JsonArray arr = doc["messages"].to<JsonArray>();

    // Only the most recent lines: the whole buffer serialises to several KB,
    // and doc + String + the async copy would peak at ~3x that on a ~40 KB heap.
    size_t startIdx = logs.size() > MAX_LOG_LINES_PER_MESSAGE ? logs.size() - MAX_LOG_LINES_PER_MESSAGE : 0;
    for (size_t i = startIdx; i < logs.size(); i++) arr.add(logs[i]);

    String response;
    serializeJson(doc, response);
    client->text(response);
}

void WebApi::run(bool mqttConnected)
{
    if (this->restartAt && (long)(millis() - this->restartAt) >= 0) {
        ESP.restart();
    }

    this->mqttConnected = mqttConnected;
    ws.cleanupClients();
    this->broadcastStats();
    this->broadcastLogs();
}
