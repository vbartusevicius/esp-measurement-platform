#include <ESP8266WiFi.h>
#include <ArduinoJson.h>
#include <algorithm>
#include "MqttClient.h"
#include "Parameter.h"
#include "Version.h"
#include "HaDiscovery.h"

extern WiFiClient network;

MqttClient::MqttClient(Storage* storage, Logger* logger, IMqttContributor* plugin, const char* pluginId, const String& deviceId)
{
    this->storage = storage;
    this->logger = logger;
    this->plugin = plugin;
    this->pluginId = pluginId;
    this->deviceId = deviceId;

    this->lastReconnectAttempt = 0;
    this->reconnectInterval = 5000;
    this->lastActivityCheck = 0;
    this->lastMqttActivity = 0;
    this->lastBrokerMessageAt = 0;
    this->previouslyConnected = false;

    // Any message from the broker (including our own status echo) confirms
    // the connection is alive end-to-end.
    client.onMessage([this](String& topic, String& payload) {
        this->lastBrokerMessageAt = millis();
    });
}

String MqttClient::getMqttErrorMessage(int errorCode)
{
    switch (errorCode) {
        case 0:
            return "Success";
        case -1:
            return "Buffer too short";
        case -2:
            return "Variable number overflow";
        case -3:
            return "Network failed to connect";
        case -4:
            return "Network timeout";
        case -5:
            return "Network failed to read";
        case -6:
            return "Network failed to write";
        case -7:
            return "Remaining length overflow";
        case -8:
            return "Remaining length mismatch";
        case -9:
            return "Missing or wrong packet";
        case -10:
            return "Connection denied";
        case -11:
            return "Failed subscription";
        case -12:
            return "Suback array overflow";
        case -13:
            return "Pong timeout";
        default:
            return "Unknown error (" + String(errorCode) + ")";
    }
}

String MqttClient::statusTopic()
{
    return "esp/" + this->deviceId + "/status";
}

String MqttClient::getBaseTopic()
{
    String topic = this->storage->getParameter(Parameter::MQTT_TOPIC);
    if (topic.isEmpty()) {
        String device = this->storage->getParameter(Parameter::MQTT_DEVICE);
        topic = device + "/stat/" + this->pluginId;
        String mutableTopic = topic;
        this->storage->saveParameter(Parameter::MQTT_TOPIC, mutableTopic);
    }
    return topic;
}

bool MqttClient::connectMqtt()
{
    String username = this->storage->getParameter(Parameter::MQTT_USER);
    String password = this->storage->getParameter(Parameter::MQTT_PASS);
    String device = this->storage->getParameter(Parameter::MQTT_DEVICE);
    String willTopic = "esp/" + this->deviceId + "/availability";

    if (client.connected()) {
        client.disconnect();
        delay(100);
    }

    client.setKeepAlive(30);
    client.setWill(willTopic.c_str(), "offline", true, 1);

    std::function<bool()> connection;

    if (username == "" && password == "") {
        connection = [device, this]() -> bool {
            return client.connect(device.c_str());
        };
    } else {
        connection = [device, username, password, this]() -> bool {
            return client.connect(device.c_str(), username.c_str(), password.c_str());
        };
    }

    auto result = connection();

    if (result) {
        client.publish(willTopic.c_str(), "online", true, 1);
        client.subscribe(this->statusTopic().c_str(), 0);
        this->logger->info("Connected to MQTT broker");
        this->reconnectInterval = 5000;
        this->updateActivityTimestamp();
        this->lastBrokerMessageAt = millis();  // grace period right after connect

        if (this->previouslyConnected) {
            this->publishHomeAssistantAutoconfig();
        }
        this->previouslyConnected = true;
    } else {
        this->logger->warning("Failed to connect to MQTT broker, error: " + this->getMqttErrorMessage(client.lastError()));
        this->reconnectInterval = (unsigned long)std::min((double)this->reconnectInterval * 1.5, 30000.0);
    }

    return result;
}

void MqttClient::begin()
{
    client.begin(
        this->storage->getParameter(Parameter::MQTT_HOST).c_str(),
        atoi(this->storage->getParameter(Parameter::MQTT_PORT).c_str()),
        network
    );

    this->connectMqtt();
    this->publishHomeAssistantAutoconfig();
}

void MqttClient::publishStatus()
{
    JsonDocument doc;
    doc["state"] = "active";
    doc["heap"] = ESP.getFreeHeap();
    doc["rssi"] = WiFi.RSSI();
    doc["uptime_s"] = millis() / 1000UL;
    doc["version"] = FW_VERSION;

    String payload;
    serializeJson(doc, payload);
    if (!this->client.publish(this->statusTopic().c_str(), payload.c_str(), false, 0)) {
        this->logger->warning("MQTT status publish failed, dropping connection");
        this->client.disconnect();
    }
}

void MqttClient::publishHomeAssistantAutoconfig()
{
    String stateTopic = this->getBaseTopic();
    this->plugin->publishHomeAssistantAutoconfig(this->client, this->deviceId, stateTopic);
    this->publishSystemHaConfig();
    this->logger->info("Published Home Assistant autodiscovery config");
}

// System-level diagnostic sensors (merged into the same HA device as plugin
// sensors via shared identifiers).
void MqttClient::publishSystemHaConfig()
{
    String statusTopic = "esp/" + this->deviceId + "/status";

    struct DiagSensorDef {
        const char* objectId;
        const char* name;
        const char* valueTemplate;
        const char* unit;
        const char* deviceClass;
        const char* icon;
    };
    static const DiagSensorDef defs[] = {
        {"heap", "Free Heap", "{{ value_json.heap | int }}", "B", nullptr, "mdi:memory"},
        {"rssi", "WiFi Signal", "{{ value_json.rssi | int }}", "dBm", "signal_strength", nullptr},
        {"uptime", "Uptime", "{{ value_json.uptime_s | int }}", "s", "duration", nullptr},
        {"version", "Firmware Version", "{{ value_json.version }}", nullptr, nullptr, "mdi:chip"},
    };

    for (auto& def : defs) {
        JsonDocument doc;
        doc["state_topic"] = statusTopic;
        doc["value_template"] = def.valueTemplate;
        doc["name"] = def.name;
        doc["unique_id"] = this->deviceId + "_" + def.objectId;
        if (def.unit) doc["unit_of_measurement"] = def.unit;
        if (def.deviceClass) doc["device_class"] = def.deviceClass;
        if (def.icon) doc["icon"] = def.icon;
        doc["entity_category"] = "diagnostic";

        JsonObject device = doc["device"].to<JsonObject>();
        HaDiscovery::addDeviceInfo(device, this->deviceId, nullptr);
        HaDiscovery::addAvailability(doc, this->deviceId);

        String json;
        serializeJson(doc, json);
        this->client.publish(("homeassistant/sensor/" + this->deviceId + "/" + def.objectId + "/config").c_str(),
                             json.c_str(), true, 1);
    }
}

void MqttClient::updateActivityTimestamp()
{
    this->lastMqttActivity = millis();
}

bool MqttClient::run()
{
    // WiFi dropped (WiFiManager is reconnecting in parallel): the MQTT socket
    // is dead anyway, so drop it locally instead of trusting a zombie socket.
    if (WiFi.status() != WL_CONNECTED) {
        if (client.connected()) {
            this->logger->warning("WiFi disconnected, dropping MQTT connection");
            client.disconnect();
        }
        return false;
    }

    bool loopOk = client.loop();

    bool isConnected = client.connected();

    if (!loopOk && isConnected) {
        // loop() failed while the client still thinks it is connected:
        // drop the dead connection so the reconnect logic kicks in.
        this->logger->warning("MQTT loop failed, dropping stale connection");
        client.disconnect();
        isConnected = false;
    }

    unsigned long now = millis();

    // Zombie watchdog: the broker stops delivering messages (and our own
    // status echo) when the connection is broken behind our back (e.g. the
    // Mosquitto container or a proxy restarted and left a half-open socket).
    if (isConnected && now - this->lastBrokerMessageAt > ZOMBIE_TIMEOUT_MS) {
        this->logger->warning("No MQTT traffic from broker for 90s, reconnecting");
        client.disconnect();
        isConnected = false;
    }

    if (now - this->lastActivityCheck >= 5000) {
        this->lastActivityCheck = now;

        if (isConnected) {
            if (now - this->lastMqttActivity >= KEEPALIVE_INTERVAL) {
                this->publishStatus();
                this->updateActivityTimestamp();
            }
        }
        else if (now - this->lastReconnectAttempt >= this->reconnectInterval) {
            this->lastReconnectAttempt = now;
            this->logger->warning("Connection to MQTT lost, reconnecting...");
            isConnected = this->connectMqtt();
        }
    }

    return isConnected;
}

bool MqttClient::isConnected()
{
    return client.connected();
}

void MqttClient::publish()
{
    if (!client.connected()) {
        return;
    }

    String topic = this->getBaseTopic();
    this->plugin->publishMqtt(this->client, topic);
    this->updateActivityTimestamp();
}
