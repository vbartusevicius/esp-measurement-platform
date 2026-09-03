#ifndef DISTANCE_PLUGIN_BASE_H
#define DISTANCE_PLUGIN_BASE_H

#include "IPlugin.h"
#include <ArduinoJson.h>
#include "IMqttContributor.h"
#include "IDisplayContributor.h"
#include "Storage.h"
#include "Logger.h"
#include "MovingAverageFilter.h"
#include "FlowRateCalculator.h"
#include "DailyUsageTracker.h"
#include <vector>

// Shared implementation for distance-based level plugins (analog / ultrasonic).
// Subclasses only provide sensor reading, distance math and sensor-specific
// parameters/HA sensors.
class DistancePluginBase : public IPlugin, public IMqttContributor, public IDisplayContributor
{
    public:
        static constexpr const char* PARAM_DISTANCE_EMPTY = "distance_empty";
        static constexpr const char* PARAM_DISTANCE_FULL = "distance_full";
        static constexpr const char* PARAM_AVG_SAMPLE_COUNT = "avg_sample_count";
        static constexpr const char* PARAM_SAMPLING_INTERVAL = "sampling_interval";
        static constexpr const char* PARAM_MAX_DELTA = "max_distance_delta";
        static constexpr const char* PARAM_TOTAL_VOLUME = "total_volume";

    protected:
        HAL* hal = nullptr;
        Storage* storage = nullptr;
        Logger* logger = nullptr;

        MovingAverageFilter distFilter;
        float measuredDistance = 0.0f;
        float relativeDistance = 0.0f;
        float absoluteDistance = 0.0f;
        bool sensorConnected = false;
        float totalVolume = 0.0f;
        float currentVolume = 0.0f;
        float lastRawDistance = 0.0f;
        FlowRateCalculator flowCalc;
        DailyUsageTracker usageTracker;

        // Configuration parsed once in setup() (changes require restart)
        int avgSampleCount = 10;
        int maxDeltaPercent = 15;
        float emptyDistM = 0.0f;
        float fullDistM = 0.0f;
        int samplingIntervalSec = 10;

        // Sensor-specific hooks
        virtual void setupPins() = 0;
        virtual void loadPluginConfig() {}
        virtual float readSensor() = 0;
        virtual float computeRelative(float measured, float emptyDist, float fullDist) const = 0;
        virtual float computeAbsolute(float measured, float emptyDist, float fullDist) const = 0;
        virtual void addPluginParameterDefs(std::vector<ParameterDef>& defs) const = 0;
        virtual const char* getDeviceName() const = 0;

        // Home Assistant discovery helpers (flow rate + volume + usage + connectivity)
        void publishCommonHaSensors(MQTTClient& client, const String& deviceId, const String& stateTopic);

    public:
        void setup(HAL* hal, Storage* storage, Logger* logger, LedController* led) override;
        void loop() override;

        void getParameterDefs(std::vector<ParameterDef>& defs) const override;
        void getStats(std::vector<StatEntry>& entries) const override;

        void publishMqtt(MQTTClient& client, const String& baseTopic) override;

        int getDisplayPageCount() const override;
        int renderDisplayPage(U8G2& u8g2, int page, int width, int height) const override;

        int getSamplingInterval() const override;

        IMqttContributor* mqtt() override { return this; }
        IDisplayContributor* display() override { return this; }
};

#endif
