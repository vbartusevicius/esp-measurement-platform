#ifndef MY_MQTT_CLIENT_H
#define MY_MQTT_CLIENT_H

#include <MQTT.h>
#include "Storage.h"
#include "Logger.h"
#include "IMqttContributor.h"
#include "RelayOutput.h"

class MqttClient
{
    private:
        Storage* storage;
        Logger* logger;
        IMqttContributor* plugin;
        RelayOutput* relay = nullptr;
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
        void publishStatus();
        void publishSystemHaConfig();
        void publishHomeAssistantAutoconfig();
        String getBaseTopic();
        String getMqttErrorMessage(int errorCode);

    public:
        MqttClient(Storage* storage, Logger* logger, IMqttContributor* plugin, const char* pluginId, const String& deviceId);
        void setRelay(RelayOutput* relay) { this->relay = relay; }
        void begin();
        bool run();
        void publish();
        bool isConnected();
};

#endif
