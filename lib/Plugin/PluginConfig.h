#ifndef PLUGIN_CONFIG_H
#define PLUGIN_CONFIG_H

class IPlugin;
class Settings;
class SensorHub;

// Configuration completeness checks: keeps Storage free of plugin knowledge.
class PluginConfig
{
    public:
        // The MQTT broker settings are in place.
        static bool deviceComplete(const Settings& storage);
        // Every required parameter of the plugin is set in its settings scope.
        static bool sensorComplete(const Settings& sensorSettings, const IPlugin& plugin);
        // At least one sensor runs, and the device and every sensor are complete.
        static bool isComplete(const Settings& storage, const SensorHub& hub);
};

#endif
