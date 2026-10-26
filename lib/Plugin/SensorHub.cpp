#include "SensorHub.h"
#include <cstring>
#include "IPlugin.h"
#include "Logger.h"
#include "Parameter.h"
#include "PluginRegistry.h"

std::vector<IPlugin*> SensorHub::parse(const String& list, const PluginRegistry& registry)
{
    std::vector<IPlugin*> plugins;
    unsigned int start = 0;
    while (start <= list.length()) {
        int comma = list.indexOf(',', start);
        unsigned int end = comma < 0 ? list.length() : (unsigned int)comma;
        String id = list.substring(start, end);
        id.trim();
        IPlugin* plugin = id.isEmpty() ? nullptr : registry.get(id.c_str());
        bool repeated = false;
        for (IPlugin* p : plugins) repeated |= p == plugin;
        if (plugin && !repeated) plugins.push_back(plugin);
        if (comma < 0) break;
        start = end + 1;
    }
    return plugins;
}

std::vector<IPlugin*> SensorHub::enabled(const Settings& storage, const PluginRegistry& registry)
{
    if (storage.hasParameter(Parameter::SENSORS)) return parse(storage.getParameter(Parameter::SENSORS), registry);
    return parse(storage.getParameter(Parameter::ACTIVE_PLUGIN, ""), registry);
}

const IPlugin* SensorHub::clash(const std::vector<IPlugin*>& plugins)
{
    uint8_t used = 0;
    for (const IPlugin* p : plugins) {
        if (used & p->inputs()) return p;
        used |= p->inputs();
    }
    return nullptr;
}

void SensorHub::begin(Settings* storage, const PluginRegistry& registry, HAL* hal, Logger* logger, LedController* led)
{
    std::vector<IPlugin*> plugins;
    for (IPlugin* p : enabled(*storage, registry)) {
        plugins.push_back(p);
        if (clash(plugins)) {
            plugins.pop_back();
            if (logger) logger->warning(String(p->getName()) + " left out: it needs an input another sensor uses");
        }
    }
    // Reserved up front: the plugins keep pointers to their settings scope.
    this->sensors.clear();
    this->sensors.reserve(plugins.size());
    for (IPlugin* p : plugins) {
        this->sensors.push_back({p, ScopedSettings(storage, ScopedSettings::prefixFor(p->getId())), 0, 0});
    }
    for (Sensor& s : this->sensors) {
        if (logger) logger->info(String("Sensor: ") + s.plugin->getName());
        s.plugin->setup(hal, &s.settings, logger, led);
    }
    if (this->sensors.empty() && logger) logger->warning("No sensor enabled. Choose one in the web interface.");
}

int SensorHub::indexOf(const char* id) const
{
    for (size_t i = 0; i < this->sensors.size(); i++) {
        if (id && strcmp(this->sensors[i].plugin->getId(), id) == 0) return (int)i;
    }
    return -1;
}

bool SensorHub::sampleDue(size_t i, unsigned long nowMs)
{
    Sensor& s = this->sensors[i];
    if ((long)(nowMs - s.nextSample) < 0) return false;
    s.nextSample = nowMs + (unsigned long)s.plugin->getSamplingInterval() * 1000UL;
    return true;
}

bool SensorHub::publishDue(size_t i, unsigned long nowMs)
{
    Sensor& s = this->sensors[i];
    if ((long)(nowMs - s.nextPublish) < 0) return false;
    s.nextPublish = nowMs + (unsigned long)s.plugin->getPublishInterval() * 1000UL;
    return true;
}
