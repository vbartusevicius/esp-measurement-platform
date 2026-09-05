#ifndef IMQTT_CONTRIBUTOR_H
#define IMQTT_CONTRIBUTOR_H

#include <Arduino.h>
#include <MQTT.h>

struct HaDiscoveryContext {
    String deviceId;
    String stateTopic;
    String availabilityTopic;
};

// Capability interface for plugins that publish to MQTT.
class IMqttContributor
{
    public:
        virtual ~IMqttContributor() = default;

        virtual void publishMqtt(MQTTClient& client, const String& baseTopic) = 0;
        virtual void publishHomeAssistantAutoconfig(MQTTClient& client, const HaDiscoveryContext& ctx) = 0;
};

#endif
