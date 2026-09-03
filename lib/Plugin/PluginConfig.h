#ifndef PLUGIN_CONFIG_H
#define PLUGIN_CONFIG_H

class Storage;
class IPlugin;

// Configuration completeness check: keeps Storage free of plugin knowledge.
class PluginConfig
{
    public:
        // true when an active plugin is selected and all required core
        // (MQTT) and plugin parameters are present in storage.
        static bool isComplete(Storage& storage, IPlugin* plugin);
};

#endif
