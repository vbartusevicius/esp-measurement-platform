#ifndef MY_MQTT_CLIENT_H
#define MY_MQTT_CLIENT_H

#include <MQTT.h>
#include "Storage.h"
#include "Logger.h"
#include "IPlugin.h"

class MqttClient
{
    private:
        Storage* storage;
        Logger* logger;
        IPlugin* plugin;
        MQTTClient client;
        String deviceId;
        unsigned long lastReconnectAttempt;
        unsigned long reconnectInterval;
        unsigned long lastActivityCheck;
        unsigned long lastMqttActivity;
        bool previouslyConnected;
        static const unsigned int KEEPALIVE_INTERVAL = 15000;

        bool connectMqtt();
        void updateActivityTimestamp();
        void publishHomeAssistantAutoconfig();
        String getBaseTopic();

    public:
        MqttClient(Storage* storage, Logger* logger, IPlugin* plugin, const String& deviceId);
        void begin();
        bool run();
        void publish();
        bool isConnected();
};

#endif
