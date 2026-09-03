#ifndef IPLUGIN_H
#define IPLUGIN_H

#include <Arduino.h>
#include <vector>

class HAL;
class Storage;
class Logger;
class LedController;
class IMqttContributor;
class IDisplayContributor;

struct ParameterDef {
    const char* key;
    const char* label;
    const char* defaultValue;
    enum Type { TEXT, NUMBER, PASSWORD } type;
    bool required;
};

struct StatEntry {
    const char* label;
    String value;
    float numericValue;
    enum Render { TEXT, PROGRESS } render;
    bool primary;
};

// Core plugin contract: identity, lifecycle, parameters and stats.
// Optional capabilities are exposed through mqtt()/display() so that
// plugins don't have to depend on the MQTT or display libraries.
class IPlugin
{
    public:
        virtual ~IPlugin() = default;

        virtual const char* getId() const = 0;
        virtual const char* getName() const = 0;

        virtual void setup(HAL* hal, Storage* storage, Logger* logger, LedController* led) = 0;
        virtual void loop() = 0;

        virtual void getParameterDefs(std::vector<ParameterDef>& defs) const = 0;

        virtual void getStats(std::vector<StatEntry>& entries) const = 0;

        virtual int getSamplingInterval() const { return 10; }

        // Optional capabilities — return nullptr if not supported.
        virtual IMqttContributor* mqtt() { return nullptr; }
        virtual IDisplayContributor* display() { return nullptr; }
};

#endif
