#ifndef RADIATION_COUNTER_PLUGIN_H
#define RADIATION_COUNTER_PLUGIN_H

#include <vector>
#include "Board.h"
#include "IMqttContributor.h"
#include "IPlugin.h"
#include "RadiationCalculator.h"
#include "RollingExtremes.h"
#include "TrendBuffer.h"

class RadiationCounterPlugin : public IPlugin, public IMqttContributor
{
    public:
        static constexpr const char* PARAM_TUBE_MODEL = "tube_model";
        static constexpr const char* PARAM_TUBE_FACTOR = "tube_conversion_factor";
        static constexpr const char* PARAM_GRAPH_RESOLUTION = "display_graph_resolution";
        static constexpr const char* PARAM_DEAD_TIME_US = "tube_dead_time_us";
        static constexpr const char* PARAM_ALERT_THRESHOLD = "alert_dose_usv_h";

        static constexpr int CNT_PIN = Board::PULSE_PIN;

    private:
        HAL* hal;
        Storage* storage;
        Logger* logger;
        LedController* led;

        // Click counter (interrupt-safe)
        volatile int clickCounter;

        // Calculator
        RadiationCalculator radCalc;

        // Configuration parsed once in setup() (changes require restart)
        float tubeFactor = 120.0f;
        int graphSpanSeconds = 600;
        float deadTimeUs = 0.0f;
        float alertThresholdUsvH = 0.3f;

        unsigned long totalCounts = 0;
        unsigned long startedAt = 0;
        unsigned long lastPulseAt = 0;
        bool pulseSeen = false;
        int lastClicks = 0;
        TrendBuffer doseTrend{1000UL};       // 56 x 1 s of dose rate
        RollingExtremes doseExtremes;        // 24 h low/high of dose rate

        static constexpr unsigned long WARMUP_MS = 60000UL;          // CPM window fill
        static constexpr unsigned long TUBE_SILENT_MS = 300000UL;    // no pulse for 5 min = tube fault

        bool tubeOk() const;
        bool warmedUp() const;

    public:
        // Chart capability for the web UI
        bool getChartData(std::vector<float>& points, int& spanSeconds) const override;

    public:
        const char* getId() const override;
        const char* getName() const override;

        void setup(HAL* hal, Storage* storage, Logger* logger, LedController* led) override;
        void loop() override;

        void getParameterDefs(std::vector<ParameterDef>& defs) const override;
        void getParameterChoices(std::vector<ParameterChoice>& choices) const override;

        void getStats(std::vector<StatEntry>& entries) const override;
        bool getScreen(ScreenModel& model) const override;

        void publishMqtt(MQTTClient& client, const String& baseTopic) override;
        void publishHomeAssistantAutoconfig(MQTTClient& client, const HaDiscoveryContext& ctx) override;

        int getSamplingInterval() const override;
        int getPublishInterval() const override;

        IMqttContributor* mqtt() override { return this; }

        // Interrupt handler (called from ISR context)
        void onRadiationClick();

    private:
        static RadiationCounterPlugin* instance;
        static IRAM_ATTR void radiationISR();
};

#endif
