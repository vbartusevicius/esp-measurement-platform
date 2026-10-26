#ifndef MY_MQTT_CLIENT_H
#define MY_MQTT_CLIENT_H

#include <Arduino.h>
#include <MQTT.h>
#include "HaDiscovery.h"
#include <WiFi.h>

class DeviceMonitor;
class Logger;
class RelayOutput;
class SensorHub;
class Storage;

class MqttClient
{
    private:
        Storage* storage;
        Logger* logger;
        SensorHub* hub;
        RelayOutput* relay = nullptr;
        DeviceMonitor* monitor = nullptr;
        int publishedRelayState = -1;
        WiFiClient network;
        MQTTClient client{(int)HaDiscovery::MQTT_BUFFER_SIZE};   // the library default (128 B) drops discovery configs
        String deviceId;
        unsigned long lastReconnectAttempt;
        unsigned long reconnectInterval;
        unsigned long lastActivityCheck;
        unsigned long lastStatusPublish;
        unsigned long lastBrokerMessageAt;
        bool previouslyConnected;
        static const unsigned long STATUS_INTERVAL_MS = 30000;
        static const unsigned long ZOMBIE_TIMEOUT_MS = 90000;

        bool connectMqtt();
        String rootTopic();
        String diagTopic();
        String availabilityTopic();
        String relayStateTopic();
        String relayCommandTopic();
        void publishRelayState();
        void publishRelayHaConfig();
        HaDiscoveryContext haContext(const String& stateTopic);
        void publishStatus();
        void publishSystemHaConfig();
        void publishHomeAssistantAutoconfig();
        String stateTopic(size_t sensor);
        String getMqttErrorMessage(int errorCode);

    public:
        // Publishes every sensor of the hub that has MQTT support, each on <device>/stat/<plugin id>.
        MqttClient(Storage* storage, Logger* logger, SensorHub* hub, const String& deviceId);
        // Relay commands go through the monitor (it refuses them while a limit rule owns the relay).
        void setRelay(RelayOutput* relay, DeviceMonitor* monitor) { this->relay = relay; this->monitor = monitor; }
        void begin();
        bool run();
        // Publishes the sensors whose publish interval has passed.
        void publish(unsigned long nowMs);
        bool isConnected();
};

#endif
