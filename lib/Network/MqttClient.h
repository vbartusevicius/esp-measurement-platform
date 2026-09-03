#ifndef MY_MQTT_CLIENT_H
#define MY_MQTT_CLIENT_H

#include <MQTT.h>
#include "Storage.h"
#include "Logger.h"
#include "IMqttContributor.h"

class MqttClient
{
    private:
        Storage* storage;
        Logger* logger;
        IMqttContributor* plugin;
        MQTTClient client;
        String deviceId;
        String pluginId;
        unsigned long lastReconnectAttempt;
        unsigned long reconnectInterval;
        unsigned long lastActivityCheck;
        unsigned long lastMqttActivity;
        unsigned long lastBrokerMessageAt;
        bool previouslyConnected;
        static const unsigned int KEEPALIVE_INTERVAL = 15000;
        // End-to-end liveness: we subscribe to our own status topic, so a
        // dead/zombie connection (broker or WiFi restart) stops delivering
        // messages and is forcefully reconnected after this timeout.
        static const unsigned long ZOMBIE_TIMEOUT_MS = 90000;

        bool connectMqtt();
        void updateActivityTimestamp();
        String statusTopic();
        void publishStatus();
        void publishSystemHaConfig();
        void publishHomeAssistantAutoconfig();
        String getBaseTopic();
        String getMqttErrorMessage(int errorCode);

    public:
        MqttClient(Storage* storage, Logger* logger, IMqttContributor* plugin, const char* pluginId, const String& deviceId);
        void begin();
        bool run();
        void publish();
        bool isConnected();
};

#endif
