#ifndef PLUGIN_REGISTRY_H
#define PLUGIN_REGISTRY_H

#include "IPlugin.h"
#include <vector>

class PluginRegistry
{
    private:
        std::vector<IPlugin*> plugins;

    public:
        void add(IPlugin* plugin);
        IPlugin* get(const char* id) const;
        IPlugin* getFirst() const;
        const std::vector<IPlugin*>& getAll() const;
        size_t count() const;
};

#endif
