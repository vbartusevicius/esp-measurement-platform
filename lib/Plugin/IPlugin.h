#ifndef IPLUGIN_H
#define IPLUGIN_H

#include <Arduino.h>
#include <vector>
#include "ScreenModel.h"

class HAL;
class Storage;
class Logger;
class LedController;
class IMqttContributor;

struct ParameterDef {
    const char* key;
    const char* label;
    const char* defaultValue;
    enum Type { TEXT, NUMBER, PASSWORD, SELECT } type;
    bool required;
};

// One option of a SELECT parameter. Choosing it fills known values into other
// parameters (e.g. a tube model sets the tube factor); the web UI applies the
// fills and the user can still override them.
struct ParameterFill {
    const char* key;
    const char* value;
};

struct ParameterChoice {
    const char* param;                  // the SELECT parameter
    const char* value;
    const char* label;
    std::vector<ParameterFill> fills;
};

struct StatEntry {
    const char* key;      // stable machine name for the web UI
    const char* label;    // human label
    String value;         // formatted, with unit
    float numericValue;
};

// Core plugin contract: identity, lifecycle, parameters and readings. MQTT is
// an optional capability (mqtt()) so plugins don't depend on the MQTT library;
// the OLED draws plugins from getScreen().
class IPlugin
{
    public:
        virtual ~IPlugin() = default;

        virtual const char* getId() const = 0;
        virtual const char* getName() const = 0;

        virtual void setup(HAL* hal, Storage* storage, Logger* logger, LedController* led) = 0;
        virtual void loop() = 0;

        virtual void getParameterDefs(std::vector<ParameterDef>& defs) const = 0;
        virtual void getParameterChoices(std::vector<ParameterChoice>& choices) const {}

        virtual void getStats(std::vector<StatEntry>& entries) const = 0;

        // Primary-measurement view for the OLED pages and the WebUI.
        virtual bool getScreen(ScreenModel& model) const { return false; }

        // Stored history for the web UI chart. Default: none.
        virtual bool getChartData(std::vector<float>& points, int& spanSeconds) const { return false; }

        virtual int getSamplingInterval() const { return 10; }
        virtual int getPublishInterval() const { return this->getSamplingInterval(); }

        // Optional capability: nullptr if not supported.
        virtual IMqttContributor* mqtt() { return nullptr; }
};

#endif
