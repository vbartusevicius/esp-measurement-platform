#include "PluginRegistry.h"

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

IPlugin* PluginRegistry::getFirst() const
{
    if (this->plugins.empty()) return nullptr;
    return this->plugins[0];
}

const std::vector<IPlugin*>& PluginRegistry::getAll() const
{
    return this->plugins;
}

size_t PluginRegistry::count() const
{
    return this->plugins.size();
}
