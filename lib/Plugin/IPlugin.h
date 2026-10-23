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
class IDisplayContributor;

struct ParameterDef {
    const char* key;
    const char* label;
    const char* defaultValue;
    enum Type { TEXT, NUMBER, PASSWORD, SELECT } type;
    bool required;
    const char* options = nullptr;   // SELECT: "value=Label;value=Label"
};

// Values a SELECT option fills into other parameters (e.g. a tube model sets
// the tube factor). The web UI applies them; the user can still override.
struct ParameterPreset {
    const char* param;    // the SELECT parameter
    const char* option;   // its option value
    const char* key;      // parameter to fill
    const char* value;
};

struct StatEntry {
    const char* label;
    String value;
    float numericValue;
    enum Render { TEXT, PROGRESS } render;
    bool primary;
    const char* key = "";   // stable machine name for the web UI (labels are for humans)
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
        virtual void getParameterPresets(std::vector<ParameterPreset>& presets) const {}

        virtual void getStats(std::vector<StatEntry>& entries) const = 0;

        virtual int getSamplingInterval() const { return 10; }

        virtual int getPublishInterval() const { return this->getSamplingInterval(); }

        // Optional history chart capability for the web UI. Default: unsupported.
        virtual bool getChartData(std::vector<float>& points, int& spanSeconds) const { return false; }

        // Primary-measurement view for the OLED pages and the WebUI.
        virtual bool getScreen(ScreenModel& model) const { return false; }

        // Optional capabilities — return nullptr if not supported.
        virtual IMqttContributor* mqtt() { return nullptr; }
        virtual IDisplayContributor* display() { return nullptr; }
};

#endif
