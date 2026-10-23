#ifndef DISTANCE_PLUGIN_BASE_H
#define DISTANCE_PLUGIN_BASE_H

#include "IPlugin.h"
#include <ArduinoJson.h>
#include "IMqttContributor.h"
#include "IDisplayContributor.h"
#include "Storage.h"
#include "Logger.h"
#include "LevelFilter.h"
#include "FlowRateCalculator.h"
#include "DailyUsageTracker.h"
#include "TrendBuffer.h"
#include "RollingExtremes.h"
#include <vector>

class DistancePluginBase : public IPlugin, public IMqttContributor, public IDisplayContributor
{
    public:
        static constexpr const char* PARAM_DISTANCE_EMPTY = "distance_empty";
        static constexpr const char* PARAM_DISTANCE_FULL = "distance_full";
        static constexpr const char* PARAM_AVG_SAMPLE_COUNT = "avg_sample_count";
        static constexpr const char* PARAM_SAMPLING_INTERVAL = "sampling_interval";
        static constexpr const char* PARAM_TOTAL_VOLUME = "total_volume";
        static constexpr const char* PARAM_DEADBAND_CM = "level_deadband_cm";
        static constexpr const char* PARAM_SNAP_SAMPLES = "step_confirm_samples";
        static constexpr const char* PARAM_MAX_RATE_CM_MIN = "max_change_cm_min";

    protected:
        HAL* hal = nullptr;
        Storage* storage = nullptr;
        Logger* logger = nullptr;

        LevelFilter distFilter;
        float measuredDistance = 0.0f;
        float relativeDistance = 0.0f;
        float absoluteDistance = 0.0f;
        bool sensorConnected = false;
        float totalVolume = 0.0f;
        float currentVolume = 0.0f;
        float lastRawDistance = 0.0f;
        FlowRateCalculator flowCalc;
        DailyUsageTracker usageTracker;
        TrendBuffer levelTrend{60000UL};     // 56 x 1 min of level %
        RollingExtremes levelExtremes;       // 24 h low/high of level %
        TrendBuffer levelHistory{900000UL, 96};   // 24 h of level %, 15 min points (web history)
        String lastSignal;                   // terminal signal of the last read (mA / echo us)

        // Configuration parsed once in setup() (changes require restart)
        int avgSampleCount = 10;
        float emptyDistM = 0.0f;
        float fullDistM = 0.0f;
        int samplingIntervalSec = 10;
        float deadbandM = 0.10f;
        int snapAfterSamples = 5;
        float maxRateMPerMin = 0.0f;

        // Sensor-specific hooks
        virtual void setupPins() = 0;
        virtual void loadPluginConfig() {}
        virtual float readSensor() = 0;
        virtual float computeRelative(float measured, float emptyDist, float fullDist) const = 0;
        virtual float computeAbsolute(float measured, float emptyDist, float fullDist) const = 0;
        virtual void addPluginParameterDefs(std::vector<ParameterDef>& defs) const = 0;
        virtual const char* getDeviceName() const = 0;

        // Home Assistant discovery helpers (flow rate + volume + usage + connectivity)
        void publishCommonHaSensors(MQTTClient& client, const HaDiscoveryContext& ctx);

    public:
        void setup(HAL* hal, Storage* storage, Logger* logger, LedController* led) override;
        void loop() override;

        void getParameterDefs(std::vector<ParameterDef>& defs) const override;
        void getStats(std::vector<StatEntry>& entries) const override;
        bool getScreen(ScreenModel& model) const override;
        bool getChartData(std::vector<float>& points, int& spanSeconds) const override;

        void publishMqtt(MQTTClient& client, const String& baseTopic) override;

        int getDisplayPageCount() const override;
        int renderDisplayPage(U8G2& u8g2, int page, int width, int height) const override;

        int getSamplingInterval() const override;

        IMqttContributor* mqtt() override { return this; }
        IDisplayContributor* display() override { return this; }
};

#endif
