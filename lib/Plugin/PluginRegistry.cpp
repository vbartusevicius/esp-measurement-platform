#include "PluginRegistry.h"
#include <cstring>
#include "IPlugin.h"

void PluginRegistry::add(IPlugin* plugin)
{
    this->plugins.push_back(plugin);
}

IPlugin* PluginRegistry::get(const char* id) const
{
    for (auto* p : this->plugins) {
        if (strcmp(p->getId(), id) == 0) {
            return p;
        }
    }
    return nullptr;
}

const std::vector<IPlugin*>& PluginRegistry::getAll() const
{
    return this->plugins;
}
