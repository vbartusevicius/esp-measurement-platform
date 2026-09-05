#ifndef RADIATION_COUNTER_PLUGIN_H
#define RADIATION_COUNTER_PLUGIN_H

#include "IPlugin.h"
#include "IMqttContributor.h"
#include "IDisplayContributor.h"
#include "Storage.h"
#include "Logger.h"
#include "LedController.h"
#include "RadiationCalculator.h"
#include <vector>

class RadiationCounterPlugin : public IPlugin, public IMqttContributor, public IDisplayContributor
{
    public:
        static constexpr const char* PARAM_TUBE_FACTOR = "tube_conversion_factor";
        static constexpr const char* PARAM_GRAPH_RESOLUTION = "display_graph_resolution";
        static constexpr const char* PARAM_DEAD_TIME_US = "tube_dead_time_us";
        static constexpr const char* PARAM_ALERT_THRESHOLD = "alert_dose_usv_h";

        static constexpr int CNT_PIN = D2;
        static constexpr int BTN_PIN = 0;

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

    public:
        // Chart capability for the web UI
        bool getChartData(std::vector<float>& points, int& spanSeconds) const override;

    private:

        // Button page counter
        volatile int buttonCounter;

    public:
        const char* getId() const override;
        const char* getName() const override;

        void setup(HAL* hal, Storage* storage, Logger* logger, LedController* led) override;
        void loop() override;

        void getParameterDefs(std::vector<ParameterDef>& defs) const override;

        void getStats(std::vector<StatEntry>& entries) const override;

        void publishMqtt(MQTTClient& client, const String& baseTopic) override;
        void publishHomeAssistantAutoconfig(MQTTClient& client, const HaDiscoveryContext& ctx) override;

        int getDisplayPageCount() const override;
        int renderDisplayPage(U8G2& u8g2, int page, int width, int height) const override;

        int getCurrentDisplayPage() const override;
        int getSamplingInterval() const override;
        int getPublishInterval() const override;

        IMqttContributor* mqtt() override { return this; }
        IDisplayContributor* display() override { return this; }

        // Interrupt handlers (called from ISR context)
        void onRadiationClick();
        void onButtonClick();

    private:
        static RadiationCounterPlugin* instance;
        static IRAM_ATTR void radiationISR();
        static IRAM_ATTR void buttonISR();

        void renderGraphPage(U8G2& u8g2, int width, int height) const;
};

#endif
