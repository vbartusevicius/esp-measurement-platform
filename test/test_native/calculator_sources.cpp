// Compile calculator and plugin implementations for the native test environment.
// The plugin code compiles against the fakes in test_native/fakes.
#include "../../lib/Plugins/AnalogDistance/AnalogDistanceCalculator.cpp"
#include "../../lib/Plugins/AnalogDistance/AnalogSensorConverter.cpp"
#include "../../lib/Plugins/UltrasonicDistance/UltrasonicDistanceCalculator.cpp"
#include "../../lib/Plugins/RadiationCounter/RadiationCalculator.cpp"
#include "../../lib/Plugin/FlowRateCalculator.cpp"
#include "../../lib/Plugin/MovingAverageFilter.cpp"
#include "../../lib/Plugin/DailyUsageTracker.cpp"
#include "../../lib/Plugins/HaDiscovery.cpp"

// Plugin implementations under test
#include "../../lib/Plugins/DistanceBase/DistancePluginBase.cpp"
#include "../../lib/Plugins/AnalogDistance/AnalogDistancePlugin.cpp"
