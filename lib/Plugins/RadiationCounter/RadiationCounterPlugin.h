#ifndef RADIATION_COUNTER_PLUGIN_H
#define RADIATION_COUNTER_PLUGIN_H

#include "IPlugin.h"
#include "Storage.h"
#include "Logger.h"
#include "LedController.h"
#include <vector>

class RadiationCounterPlugin : public IPlugin
{
    public:
        static constexpr const char* PARAM_TUBE_FACTOR = "tube_conversion_factor";
        static constexpr const char* PARAM_GRAPH_RESOLUTION = "display_graph_resolution";

        static constexpr int CNT_PIN = D2;
        static constexpr int BTN_PIN = 0;

    private:
        static const int CALCULATOR_BUFFER_SIZE = 60;
        static const int GRAPH_BUFFER_SIZE = 128;

        Storage* storage;
        Logger* logger;
        LedController* led;

        // Click counter (interrupt-safe)
        volatile int clickCounter;

        // Calculator state
        std::vector<int> calcBuffer;
        int cpm;
        float dose;

        // Aggregator state for graph
        int spanPointer;
        std::vector<float> spanBuffer;
        std::vector<float> graphBuffer;

        // Button page counter
        volatile int buttonCounter;

        void calculate(int clicks);
        void aggregateGraph();

    public:
        const char* getId() const override;
        const char* getName() const override;

        void setup(Storage* storage, Logger* logger, LedController* led) override;
        void loop() override;

        void getParameterDefs(std::vector<ParameterDef>& defs) const override;
        std::vector<const char*> getRequiredParameters() const override;

        void getStats(JsonDocument& doc) const override;

        void publishMqtt(MQTTClient& client, const String& baseTopic) override;
        void publishHomeAssistantAutoconfig(MQTTClient& client, const String& deviceId, const String& stateTopic) override;

        int getDisplayPageCount() const override;
        void renderDisplayPage(U8G2& u8g2, int page, int width, int height) const override;

        int getCurrentDisplayPage() const override;
        int getSamplingInterval() const override;

        // Interrupt handlers (called from ISR context)
        void onRadiationClick();
        void onButtonClick();

    private:
        static RadiationCounterPlugin* instance;
        static void IRAM_ATTR radiationISR();
        static void IRAM_ATTR buttonISR();

        void renderGraphPage(U8G2& u8g2, int width, int height) const;
        void renderInfoPage(U8G2& u8g2, int width, int height) const;
};

#endif
