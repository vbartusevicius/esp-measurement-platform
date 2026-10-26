#include "PluginConfig.h"
#include <vector>
#include "IPlugin.h"
#include "Parameter.h"
#include "SensorHub.h"
#include "Settings.h"

bool PluginConfig::deviceComplete(const Settings& storage)
{
    return storage.hasParameter(Parameter::MQTT_HOST) && storage.hasParameter(Parameter::MQTT_PORT) &&
           storage.hasParameter(Parameter::MQTT_DEVICE);
}

bool PluginConfig::sensorComplete(const Settings& sensorSettings, const IPlugin& plugin)
{
    std::vector<ParameterDef> defs;
    plugin.getParameterDefs(defs);
    for (const ParameterDef& def : defs) {
        if (def.required && !sensorSettings.hasParameter(def.key)) return false;
    }
    return true;
}

bool PluginConfig::isComplete(const Settings& storage, const SensorHub& hub)
{
    if (hub.size() == 0 || !deviceComplete(storage)) return false;
    for (size_t i = 0; i < hub.size(); i++) {
        if (!sensorComplete(hub.settings(i), hub.plugin(i))) return false;
    }
    return true;
}
