#include "WebApi.h"
#include <cmath>
#include "Parameter.h"
#include "ChipId.h"
#include "TimeHelper.h"
#include "Version.h"
#include "PlatformWiFi.h"
#include "WebAssets.h"
#if defined(ESP32)
#include <Update.h>
static String updateError() { return String(Update.errorString()); }
#else
#include <Updater.h>
static String updateError() { return String(Update.getErrorString()); }
#endif

static float rounded(float v) { return roundf(v * 100.0f) / 100.0f; }

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
    this->setupWebSocket();
    this->setupApiEndpoints();
    this->setupUploadEndpoint();
    this->setupStaticFiles();

    server.begin();
    this->logger->info("Web server started");
}

void WebApi::setupStaticFiles() {
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
        doc["limit_low"] = this->storage->getParameter(Parameter::LIMIT_LOW, "");
        doc["limit_high"] = this->storage->getParameter(Parameter::LIMIT_HIGH, "");
        doc["limit_hysteresis"] = this->storage->getParameter(Parameter::LIMIT_HYSTERESIS, "");
        if (this->monitor) {
            doc["limit_low_on"] = this->monitor->limitEnabled(Parameter::LIMIT_LOW_ON, Parameter::LIMIT_LOW) ? "1" : "0";
            doc["limit_high_on"] = this->monitor->limitEnabled(Parameter::LIMIT_HIGH_ON, Parameter::LIMIT_HIGH) ? "1" : "0";
        }
        doc["relay_mode"] = this->storage->getParameter(Parameter::RELAY_MODE, "manual");
        doc["relay_available"] = this->monitor && this->monitor->relayAvailable();

        // Plugin parameter values and definitions
        std::vector<ParameterDef> defs;
        std::vector<ParameterPreset> presets;
        if (pluginToInspect) {
            pluginToInspect->getParameterDefs(defs);
            pluginToInspect->getParameterPresets(presets);
        }
        
        JsonArray paramDefs = doc["plugin_params"].to<JsonArray>();

        for (auto& def : defs) {
            JsonObject obj = paramDefs.add<JsonObject>();
            obj["key"] = def.key;
            obj["label"] = def.label;
            obj["default"] = def.defaultValue;
            obj["type"] = def.type == ParameterDef::NUMBER ? "number" :
                          def.type == ParameterDef::PASSWORD ? "password" :
                          def.type == ParameterDef::SELECT ? "select" : "text";
            if (def.options) {
                // "value=Label;value=Label" -> [{value, label}]
                JsonArray options = obj["options"].to<JsonArray>();
                String all = def.options;
                int start = 0;
                while (start < (int)all.length()) {
                    int end = all.indexOf(';', start);
                    if (end < 0) end = all.length();
                    String item = all.substring(start, end);
                    int eq = item.indexOf('=');
                    JsonObject option = options.add<JsonObject>();
                    option["value"] = eq < 0 ? item : item.substring(0, eq);
                    option["label"] = eq < 0 ? item : item.substring(eq + 1);
                    start = end + 1;
                }
            }
            for (auto& preset : presets) {
                if (strcmp(preset.param, def.key) == 0) obj["presets"][preset.option][preset.key] = preset.value;
            }
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
                this->pendingLimitsReload = true;
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
        this->fillStatus(doc);
        serializeJson(doc, *response);
        request->send(response);
    });

    // POST /api/v1/relay?state=on|off - manual relay control
    server.on("/api/v1/relay", HTTP_POST, [this](AsyncWebServerRequest *request) {
        if (!this->monitor || !this->monitor->relayAvailable()) {
            request->send(404, "application/json", "{\"status\":\"error\",\"message\":\"No relay on this board\"}");
            return;
        }
        if (this->monitor->limits().relayMode() != LimitMonitor::RelayMode::MANUAL) {
            request->send(409, "application/json", "{\"status\":\"error\",\"message\":\"Relay follows the limit rule\"}");
            return;
        }
        String state = request->hasParam("state") ? request->getParam("state")->value() : String();
        bool on = false;
        if (!RelayOutput::parseCommand(state.c_str(), on)) {
            request->send(400, "application/json", "{\"status\":\"error\",\"message\":\"state must be on or off\"}");
            return;
        }
        this->pendingRelay = on ? 1 : 0;
        request->send(200, "application/json", "{\"status\":\"ok\"}");
    });

    // POST /api/v1/display?action=page|dismiss - same as the PAGE button
    server.on("/api/v1/display", HTTP_POST, [this](AsyncWebServerRequest *request) {
        String action = request->hasParam("action") ? request->getParam("action")->value() : String();
        if (action == "page") this->pendingPage = true;
        else if (action == "dismiss") this->pendingDismiss = true;
        else {
            request->send(400, "application/json", "{\"status\":\"error\",\"message\":\"action must be page or dismiss\"}");
            return;
        }
        request->send(200, "application/json", "{\"status\":\"ok\"}");
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
            ScreenModel screen;
            doc["unit"] = this->activePlugin->getScreen(screen) ? screen.unit : "";
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

        const int command = U_FLASH;
#if defined(ESP32)
        const size_t maxSize = UPDATE_SIZE_UNKNOWN;   // the target partition bounds the image
#else
        const size_t maxSize = (ESP.getFreeSketchSpace() - 0x1000) & 0xFFFFF000;
        Update.runAsync(true);
#endif

        if (!Update.begin(maxSize, command)) {
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
    this->fillStatus(doc);

    String message;
    serializeJson(doc, message);
    ws.textAll(message);
}

static void addNumber(JsonObject obj, const char* key, float value)
{
    if (std::isnan(value)) obj[key] = nullptr;
    else obj[key] = value;
}

void WebApi::fillStatus(JsonDocument& doc) {
    doc["chip_id"] = ChipId::get();
    doc["active_plugin"] = this->activePlugin ? this->activePlugin->getId() : "";
    doc["active_plugin_name"] = this->activePlugin ? this->activePlugin->getName() : "None";
    doc["wifi_network"] = WiFi.SSID();
    doc["wifi_signal"] = String(WiFi.RSSI());
    doc["ip_address"] = WiFi.localIP().toString();
    doc["free_heap"] = ESP.getFreeHeap();
    doc["mqtt_connected"] = this->mqttConnected;
    doc["firmware_version"] = FW_VERSION;
    doc["errors"] = this->logger->errors();
    doc["warnings"] = this->logger->warnings();

    char uptimeBuf[32];
    TimeHelper::getUptime(uptimeBuf);
    doc["uptime"] = uptimeBuf;
    doc["uptime_s"] = millis() / 1000UL;

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
        obj["key"] = e.key;
    }

    // Primary-measurement view shared with the OLED pages
    ScreenModel screen;
    if (this->activePlugin && this->activePlugin->getScreen(screen)) {
        JsonObject s = doc["screen"].to<JsonObject>();
        s["kind"] = screen.kind;
        s["title"] = screen.title;
        addNumber(s, "value", screen.value);
        s["text"] = screen.format(screen.value);
        s["unit"] = screen.unit;
        s["decimals"] = screen.decimals;
        s["valid"] = screen.valid;
        addNumber(s, "scale_min", screen.scaleMin);
        addNumber(s, "scale_max", screen.scaleMax);
        s["trend_bucket_s"] = screen.trendBucketSec;
        JsonArray trend = s["trend"].to<JsonArray>();
        for (float v : screen.trend) trend.add(rounded(v));
        JsonArray lines = s["lines"].to<JsonArray>();
        for (auto& line : screen.lines) {
            JsonObject l = lines.add<JsonObject>();
            l["label"] = line.label;
            l["value"] = line.value;
        }
        s["sensor_label"] = screen.sensorLabel;
        s["sensor_ok"] = screen.sensorOk;
        s["raw"] = screen.raw;
        s["signal"] = screen.signal;
        addNumber(s, "low_24h", screen.low24);
        addNumber(s, "high_24h", screen.high24);
    }

    if (this->monitor) {
        const LimitMonitor& limits = this->monitor->limits();
        JsonObject lim = doc["limits"].to<JsonObject>();
        addNumber(lim, "low", limits.low());
        addNumber(lim, "high", limits.high());
        lim["state"] = LimitMonitor::stateName(limits.state());
        lim["alert"] = limits.alertPending();
        lim["trips"] = limits.trips();

        JsonObject relay = doc["relay"].to<JsonObject>();
        relay["available"] = this->monitor->relayAvailable();
        relay["on"] = this->monitor->relayOn();
        relay["activations"] = this->monitor->relayActivations();
        relay["mode"] = LimitMonitor::modeName(limits.relayMode());

        const EventLog& events = this->monitor->events();
        JsonArray arr = doc["events"].to<JsonArray>();
        for (size_t i = 0; i < events.size(); i++) {
            const EventLog::Entry& e = events.newest(i);
            JsonObject obj = arr.add<JsonObject>();
            obj["t"] = e.uptimeSec;
            obj["title"] = e.title;
            obj["detail"] = e.detail;
        }
    }

    if (this->display) {
        JsonObject d = doc["display"].to<JsonObject>();
        d["portrait"] = this->display->isPortrait();
        d["page"] = this->display->getPage();
        d["pages"] = this->display->isPortrait() ? Display::PORTRAIT_PAGES : 1;
    }
}

void WebApi::setDevice(DeviceMonitor* monitor, Display* display, ActionCallback pagePress) {
    this->monitor = monitor;
    this->display = display;
    this->pagePress = pagePress;
}

void WebApi::processActions() {
    if (this->pendingLimitsReload) {
        this->pendingLimitsReload = false;
        if (this->monitor) this->monitor->loadLimits();
    }
    int relay = this->pendingRelay;
    if (relay >= 0) {
        this->pendingRelay = -1;
        if (this->monitor) this->monitor->commandRelay(relay == 1, "WEB UI", millis());
    }
    if (this->pendingDismiss) {
        this->pendingDismiss = false;
        if (this->monitor) this->monitor->dismissAlert();
    }
    if (this->pendingPage) {
        this->pendingPage = false;
        if (this->pagePress) this->pagePress();
    }
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
