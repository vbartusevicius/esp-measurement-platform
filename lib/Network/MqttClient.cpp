#include "MqttClient.h"
#include <algorithm>
#include "DeviceMonitor.h"
#include "IMqttContributor.h"
#include "Logger.h"
#include "Parameter.h"
#include "RelayOutput.h"
#include "Storage.h"
#include "Version.h"

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
    this->lastStatusPublish = 0;
    this->lastBrokerMessageAt = 0;
    this->previouslyConnected = false;

    // Any message from the broker (including our own status echo) confirms
    // the connection is alive end-to-end.
    client.onMessage([this](String& topic, String& payload) {
        this->lastBrokerMessageAt = millis();
        bool on = false;
        if (this->relay && topic == this->relayCommandTopic() && RelayOutput::parseCommand(payload.c_str(), on)) {
            if (this->monitor) this->monitor->commandRelay(on, "MQTT", millis());
            else this->relay->set(on);
            this->publishRelayState();   // also corrects HA if the command was refused
        }
    });
}

String MqttClient::relayStateTopic()
{
    return this->rootTopic() + "/relay";
}

String MqttClient::relayCommandTopic()
{
    return this->rootTopic() + "/relay/set";
}

void MqttClient::publishRelayState()
{
    if (!this->relay) return;
    this->publishedRelayState = this->relay->isOn() ? 1 : 0;
    this->client.publish(this->relayStateTopic().c_str(), this->relay->isOn() ? "ON" : "OFF", true, 1);
}

HaDiscoveryContext MqttClient::haContext(const String& stateTopic)
{
    HaDiscoveryContext ctx;
    ctx.deviceId = this->deviceId;
    ctx.stateTopic = stateTopic;
    ctx.availabilityTopic = this->availabilityTopic();
    ctx.deviceName = this->storage->getParameter(Parameter::DEVICE_NAME, "");
    return ctx;
}

void MqttClient::publishRelayHaConfig()
{
    if (!this->relay) return;
    static const HaEntity relaySwitch = {"switch", "relay", "relay", "Relay", nullptr, nullptr, nullptr, "mdi:electric-switch", false, false};
    HaDiscovery::publish(this->client, this->haContext(this->relayStateTopic()), relaySwitch, nullptr,
                         [](JsonDocument& doc, const HaDiscoveryContext& ctx) {
                             doc["command_topic"] = ctx.stateTopic + "/set";
                             doc["payload_on"] = "ON";
                             doc["payload_off"] = "OFF";
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

String MqttClient::rootTopic()
{
    String device = this->storage->getParameter(Parameter::MQTT_DEVICE);
    return device.isEmpty() ? ("esp_" + this->deviceId) : device;
}

String MqttClient::diagTopic()
{
    return this->rootTopic() + "/diag";
}

String MqttClient::availabilityTopic()
{
    return this->rootTopic() + "/availability";
}

String MqttClient::getBaseTopic()
{
    String topic = this->storage->getParameter(Parameter::MQTT_TOPIC);
    if (topic.isEmpty()) {
        topic = this->rootTopic() + "/stat/" + this->pluginId;
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
    String willTopic = this->availabilityTopic();

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
        client.subscribe(this->diagTopic().c_str(), 0);
        if (this->relay) {
            client.subscribe(this->relayCommandTopic().c_str(), 1);
            this->publishRelayState();
        }
        this->logger->info("Connected to MQTT broker");
        this->reconnectInterval = 5000;
        this->lastBrokerMessageAt = millis();  // grace period right after connect

        if (this->previouslyConnected) {
            this->publishHomeAssistantAutoconfig();
        }
        this->previouslyConnected = true;
        this->lastStatusPublish = millis();
        this->publishStatus();
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
        this->network
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
    if (this->relay) doc["relay"] = this->relay->isOn() ? "ON" : "OFF";

    String payload;
    serializeJson(doc, payload);
    if (!this->client.publish(this->diagTopic().c_str(), payload.c_str(), false, 0)) {
        this->logger->warning("MQTT status publish failed, dropping connection");
        this->client.disconnect();
    }
}

void MqttClient::publishHomeAssistantAutoconfig()
{
    this->plugin->publishHomeAssistantAutoconfig(this->client, this->haContext(this->getBaseTopic()));
    this->publishSystemHaConfig();
    this->publishRelayHaConfig();
    this->logger->info("Published Home Assistant autodiscovery config");
}

// System-level diagnostic sensors (merged into the same HA device as plugin
// sensors via shared identifiers).
void MqttClient::publishSystemHaConfig()
{
    static const HaEntity diagnostics[] = {
        {"sensor", "heap", "heap", "Free Heap", "{{ value_json.heap | int }}", "B", "data_size", "mdi:memory", true, true},
        {"sensor", "rssi", "rssi", "WiFi Signal", "{{ value_json.rssi | int }}", "dBm", "signal_strength", nullptr, true, true},
        {"sensor", "uptime", "uptime", "Uptime", "{{ value_json.uptime_s | int }}", "s", "duration", nullptr, true, true},
    };
    const HaDiscoveryContext ctx = this->haContext(this->diagTopic());
    for (const HaEntity& entity : diagnostics) HaDiscovery::publish(this->client, ctx, entity, nullptr);
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

    // Relay switched by a limit rule or the WebUI since the last publish
    if (this->relay && client.connected() && this->publishedRelayState != (this->relay->isOn() ? 1 : 0)) {
        this->publishRelayState();
    }

    bool isConnected = client.connected();

    if (!loopOk && isConnected) {
        // loop() failed while the client still thinks it is connected:
        // drop the dead connection so the reconnect logic kicks in.
        this->logger->warning("MQTT loop failed, dropping stale connection");
        client.disconnect();
        isConnected = false;
    }

    unsigned long now = millis();

    if (isConnected && now - this->lastBrokerMessageAt > ZOMBIE_TIMEOUT_MS) {
        this->logger->warning("No MQTT traffic from broker for 90s, reconnecting");
        client.disconnect();
        isConnected = false;
    }

    if (now - this->lastActivityCheck >= 5000) {
        this->lastActivityCheck = now;

        if (isConnected) {
            if (now - this->lastStatusPublish >= STATUS_INTERVAL_MS) {
                this->lastStatusPublish = now;
                this->publishStatus();
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
}
