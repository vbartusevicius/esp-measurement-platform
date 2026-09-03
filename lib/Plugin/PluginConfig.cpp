#include "PluginConfig.h"
#include "Storage.h"
#include "Parameter.h"
#include "IPlugin.h"
#include <vector>

bool PluginConfig::isComplete(Storage& storage, IPlugin* plugin)
{
    // If no plugin is selected, the device is unconfigured
    if (!plugin) return false;

    // Core required parameters
    if (!storage.hasParameter(Parameter::MQTT_HOST)) return false;
    if (!storage.hasParameter(Parameter::MQTT_PORT)) return false;
    if (!storage.hasParameter(Parameter::MQTT_DEVICE)) return false;

    // Plugin-specific required parameters (single source: ParameterDef.required)
    std::vector<ParameterDef> defs;
    plugin->getParameterDefs(defs);
    for (auto& def : defs) {
        if (def.required && !storage.hasParameter(def.key)) return false;
    }

    return true;
}
