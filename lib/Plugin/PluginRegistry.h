#ifndef PLUGIN_REGISTRY_H
#define PLUGIN_REGISTRY_H

#include <vector>

class IPlugin;

class PluginRegistry
{
    private:
        std::vector<IPlugin*> plugins;

    public:
        void add(IPlugin* plugin);
        IPlugin* get(const char* id) const;
        const std::vector<IPlugin*>& getAll() const;
};

#endif
