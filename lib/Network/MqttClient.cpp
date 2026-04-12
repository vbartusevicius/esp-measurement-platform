#include <ESP8266WiFi.h>
#include <ArduinoJson.h>
#include <algorithm>
#include "MqttClient.h"
#include "Parameter.h"

extern WiFiClient network;

MqttClient::MqttClient(Storage* storage, Logger* logger, IPlugin* plugin, const String& deviceId)
{
    this->storage = storage;
    this->logger = logger;
    this->plugin = plugin;
    this->deviceId = deviceId;

    this->lastReconnectAttempt = 0;
    this->reconnectInterval = 5000;
    this->lastActivityCheck = 0;
    this->lastMqttActivity = 0;
    this->previouslyConnected = false;
}

String MqttClient::getBaseTopic()
{
    String topic = this->storage->getParameter(Parameter::MQTT_TOPIC);
    if (topic.isEmpty()) {
        String device = this->storage->getParameter(Parameter::MQTT_DEVICE);
        topic = device + "/stat/" + String(this->plugin->getId());
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

    client.setKeepAlive(60);
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
        this->logger->info("Connected to MQTT broker");
        this->reconnectInterval = 5000;
        this->updateActivityTimestamp();

        if (this->previouslyConnected) {
            this->publishHomeAssistantAutoconfig();
        }
        this->previouslyConnected = true;
    } else {
        this->logger->warning("Failed to connect to MQTT broker, error: " + String(client.lastError()));
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

void MqttClient::publishHomeAssistantAutoconfig()
{
    String stateTopic = this->getBaseTopic();
    this->plugin->publishHomeAssistantAutoconfig(this->client, this->deviceId, stateTopic);
    this->logger->info("Published Home Assistant autodiscovery config");
}

void MqttClient::updateActivityTimestamp()
{
    this->lastMqttActivity = millis();
}

bool MqttClient::run()
{
    client.loop();

    bool isConnected = client.connected();
    unsigned long now = millis();

    if (now - this->lastActivityCheck >= 5000) {
        this->lastActivityCheck = now;

        if (isConnected) {
            if (now - this->lastMqttActivity >= KEEPALIVE_INTERVAL) {
                String statusTopic = "esp/" + this->deviceId + "/status";
                client.publish(statusTopic.c_str(), String("active," + String(ESP.getFreeHeap())).c_str(), false, 0);
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
