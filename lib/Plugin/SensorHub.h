#ifndef SENSOR_HUB_H
#define SENSOR_HUB_H

#include <Arduino.h>
#include <vector>
#include "ScopedSettings.h"

class HAL;
class IPlugin;
class LedController;
class Logger;
class PluginRegistry;

// The sensors running side by side: the enabled plugins in display order,
// each with its own settings scope and sampling / publishing schedule.
class SensorHub
{
    public:
        struct Sensor {
            IPlugin* plugin;
            ScopedSettings settings;
            unsigned long nextSample;
            unsigned long nextPublish;
        };

        // Enabled plugins from Parameter::SENSORS ("analog_distance,pulse_meter"),
        // or the single pre-multi-sensor ACTIVE_PLUGIN when that is all there is.
        static std::vector<IPlugin*> enabled(const Settings& storage, const PluginRegistry& registry);
        // Unknown ids and repeats are dropped.
        static std::vector<IPlugin*> parse(const String& list, const PluginRegistry& registry);
        // The first plugin that needs a board input an earlier one already uses, or nullptr.
        static const IPlugin* clash(const std::vector<IPlugin*>& plugins);

        // Sets up the enabled sensors (a clashing one is left out and logged).
        void begin(Settings* storage, const PluginRegistry& registry, HAL* hal, Logger* logger, LedController* led);

        size_t size() const { return this->sensors.size(); }
        IPlugin& plugin(size_t i) const { return *this->sensors[i].plugin; }
        ScopedSettings& settings(size_t i) { return this->sensors[i].settings; }
        const ScopedSettings& settings(size_t i) const { return this->sensors[i].settings; }
        int indexOf(const char* id) const;

        // true when sensor i should sample / publish now (and schedules the next time)
        bool sampleDue(size_t i, unsigned long nowMs);
        bool publishDue(size_t i, unsigned long nowMs);

    private:
        std::vector<Sensor> sensors;
};

#endif
