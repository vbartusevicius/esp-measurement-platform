#ifndef MY_MQTT_CLIENT_H
#define MY_MQTT_CLIENT_H

#include <Arduino.h>
#include <MQTT.h>
#include "HaDiscovery.h"
#include "PlatformWiFi.h"

class DeviceMonitor;
class IMqttContributor;
class Logger;
class RelayOutput;
class Storage;

class MqttClient
{
    private:
        Storage* storage;
        Logger* logger;
        IMqttContributor* plugin;
        RelayOutput* relay = nullptr;
        DeviceMonitor* monitor = nullptr;
        int publishedRelayState = -1;
        WiFiClient network;
        MQTTClient client;
        String deviceId;
        String pluginId;
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
        String getBaseTopic();
        String getMqttErrorMessage(int errorCode);

    public:
        MqttClient(Storage* storage, Logger* logger, IMqttContributor* plugin, const char* pluginId, const String& deviceId);
        // Relay commands go through the monitor (it refuses them while a limit rule owns the relay).
        void setRelay(RelayOutput* relay, DeviceMonitor* monitor) { this->relay = relay; this->monitor = monitor; }
        void begin();
        bool run();
        void publish();
        bool isConnected();
};

#endif
