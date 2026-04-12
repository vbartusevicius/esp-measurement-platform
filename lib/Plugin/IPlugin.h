#ifndef IPLUGIN_H
#define IPLUGIN_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <MQTT.h>
#include <U8g2lib.h>
#include <vector>

class Storage;
class Logger;
class LedController;

struct ParameterDef {
    const char* key;
    const char* label;
    const char* defaultValue;
    enum Type { TEXT, NUMBER, PASSWORD } type;
    bool required;
};

class IPlugin
{
    public:
        virtual ~IPlugin() = default;

        virtual const char* getId() const = 0;
        virtual const char* getName() const = 0;

        virtual void setup(Storage* storage, Logger* logger, LedController* led) = 0;
        virtual void loop() = 0;

        virtual void getParameterDefs(std::vector<ParameterDef>& defs) const = 0;
        virtual std::vector<const char*> getRequiredParameters() const = 0;

        virtual void getStats(JsonDocument& doc) const = 0;

        virtual void publishMqtt(MQTTClient& client, const String& baseTopic) = 0;
        virtual void publishHomeAssistantAutoconfig(MQTTClient& client, const String& deviceId, const String& stateTopic) = 0;

        virtual int getDisplayPageCount() const = 0;
        virtual int getCurrentDisplayPage() const { return 0; }
        virtual void renderDisplayPage(U8G2& u8g2, int page, int width, int height) const = 0;

        virtual int getSamplingInterval() const { return 10; }
};

#endif
