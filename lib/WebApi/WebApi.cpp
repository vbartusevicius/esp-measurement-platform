#include "WebApi.h"
#include "ConfigJson.h"
#include "DeviceMonitor.h"
#include "Logger.h"
#include "PluginRegistry.h"
#include "RelayOutput.h"
#include "SensorHub.h"
#include "StatusJson.h"
#include "Storage.h"
#include "WebAssets.h"
#include <Update.h>
#include "FirmwareImage.h"
#include "Parameter.h"

static String updateError() { return String(Update.errorString()); }

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

WebApi::WebApi(Storage* storage, Logger* logger, SensorHub* hub, PluginRegistry* registry,
               DeviceMonitor* monitor, ResetCallback resetCallback)
    : server(80), ws("/ws"), storage(storage), logger(logger), hub(hub),
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
            AsyncWebServerResponse *response = request->beginResponse(200, asset->mime, asset->gzip, asset->length);
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
    // Device settings and every sensor type (enabled or not) with its parameters and limits
    server.on("/api/v1/config", HTTP_GET, [this](AsyncWebServerRequest *request) {
        JsonDocument doc;
        ConfigJson::writeConfig(doc, *this->storage, *this->registry, this->monitor);
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
        StatusJson::writeChart(doc, *this->hub, this->sensorParam(request));
        sendJson(request, doc);
    });

    // POST /api/v1/relay?state=on|off - manual relay control
    server.on("/api/v1/relay", HTTP_POST, [this](AsyncWebServerRequest *request) {
        this->handleRelay(request);
    });

    // ?sensor=<id> acknowledges that sensor's alert, without it every pending one
    server.on("/api/v1/alert/ack", HTTP_POST, [this](AsyncWebServerRequest *request) {
        this->pendingAlertAck = request->hasParam("sensor") ? this->sensorParam(request) : -1;
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

int WebApi::sensorParam(AsyncWebServerRequest* request) const
{
    if (!request->hasParam("sensor")) return 0;
    return this->hub->indexOf(request->getParam("sensor")->value().c_str());
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
    const char* problem = ConfigJson::problem(doc.as<JsonObjectConst>(), *this->registry);
    if (problem) {
        sendResult(request, 400, problem);
        return;
    }
    for (JsonPair kv : doc.as<JsonObject>()) {
        String value = kv.value().as<String>();
        // The UI never receives the password, so an empty field means "keep it".
        if (value.length() == 0 && strcmp(kv.key().c_str(), Parameter::MQTT_PASS) == 0) continue;
        this->storage->saveParameter(kv.key().c_str(), value);
    }
    // Once the sensor list is saved, the single-sensor setting it replaced is dropped
    // (otherwise switching every sensor off would bring that one back).
    if (doc[Parameter::SENSORS].is<const char*>()) {
        String none;
        this->storage->saveParameter(Parameter::ACTIVE_PLUGIN, none);
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
    if (this->monitor->relayMode() != LimitMonitor::RelayMode::MANUAL) {
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
            if (this->uploadRejected) {
                sendResult(request, 400, this->uploadRejected);
                return;
            }
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
        // The web UI is part of firmware.bin, so firmware is the only target.
        this->logger->info(String("Upload started: ") + filename +
                           " free=" + String(ESP.getFreeHeap()) +
                           " maxBlock=" + String(ESP.getMaxAllocHeap()));
        this->uploadRejected = FirmwareImage::problem(FirmwareImage::classify(data, len));
        if (this->uploadRejected) {
            this->logger->error(String("Upload refused: ") + this->uploadRejected);
            return;
        }

        // Free the websocket buffers: Update.begin() needs 4 KB contiguous.
        ws.closeAll();
        ws.enable(false);

        if (!Update.begin(UPDATE_SIZE_UNKNOWN, U_FLASH)) {   // the OTA partition bounds the image
            this->logger->error("Update.begin failed: " + updateError());
        }
    }

    if (this->uploadRejected || Update.hasError()) return;

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
    StatusJson::write(doc, {this->hub, this->logger, this->monitor, this->storage, this->mqttConnected});
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
    const int ack = this->pendingAlertAck;
    if (ack != -2) {
        this->pendingAlertAck = -2;
        if (ack == -1) this->monitor->dismissAll();
        else if (ack >= 0) this->monitor->dismissAlert((size_t)ack);
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
