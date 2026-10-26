#ifndef PULSE_METER_PLUGIN_H
#define PULSE_METER_PLUGIN_H

#include <vector>
#include "Board.h"
#include "IMqttContributor.h"
#include "IPlugin.h"
#include "RollingExtremes.h"
#include "TrendBuffer.h"

// Volume meter (water, gas, oil, ...) giving one pulse per K litres on IO4
// (sensor pole 8): our optical dial reader, a B METERS IWM-PL3, a gas meter's
// reed contact, any open-collector or push-pull 3.3-5 V pulse. The board's
// 4.7k pull-up makes a closing contact a falling edge.
//
// Keeps the meter's register (total m3, set once from the meter's dial and
// persisted), flow rate from the pulse interval, rolling 24 h usage, a 24 h
// history in 15 min bars and a continuous-flow (leak) flag.
class PulseMeterPlugin : public IPlugin, public IMqttContributor
{
    public:
        static constexpr const char* PARAM_MEDIUM = "meter_medium";
        static constexpr const char* PARAM_LITERS_PER_PULSE = "meter_liters_per_pulse";
        static constexpr const char* PARAM_METER_READING = "meter_reading_m3";
        static constexpr const char* PARAM_MIN_PULSE_GAP_MS = "meter_min_pulse_gap_ms";
        static constexpr const char* PARAM_LEAK_HOURS = "meter_leak_hours";
        // Internal state, not shown in the settings
        static constexpr const char* KEY_TOTAL_LITERS = "meter_total_l";
        static constexpr const char* KEY_READING_APPLIED = "meter_reading_applied";

        static constexpr int PULSE_PIN = Board::METER_PULSE_PIN;
        static constexpr unsigned long PERSIST_INTERVAL_MS = 600000UL;   // flash write at most every 10 min
        static constexpr unsigned long FLOW_TIMEOUT_MS = 600000UL;       // no pulse for 10 min = no flow
        static constexpr int HISTORY_BARS = 96;                           // 24 h of 15 min bars
        static constexpr unsigned long HISTORY_BAR_MS = 900000UL;
        static constexpr int USAGE_HOURS = 24;

        const char* getId() const override;
        const char* getName() const override;
        uint8_t inputs() const override { return Board::INPUT_IO4; }

        void setup(HAL* hal, Settings* storage, Logger* logger, LedController* led) override;
        void loop() override;

        void getParameterDefs(std::vector<ParameterDef>& defs) const override;
        void getParameterChoices(std::vector<ParameterChoice>& choices) const override;
        void getStats(std::vector<StatEntry>& entries) const override;
        bool getScreen(ScreenModel& model) const override;
        bool getChartData(std::vector<float>& points, int& spanSeconds) const override;

        void publishMqtt(MQTTClient& client, const String& baseTopic) override;
        void publishHomeAssistantAutoconfig(MQTTClient& client, const HaDiscoveryContext& ctx) override;

        int getSamplingInterval() const override { return 1; }
        int getPublishInterval() const override { return 30; }
        IMqttContributor* mqtt() override { return this; }

        // Pulse edge at nowMs (the ISR passes millis()); edges closer than the
        // minimum gap to the last counted one are contact noise and ignored.
        IRAM_ATTR void onPulse(unsigned long nowMs);

        double totalLiters() const { return this->total; }
        float flowLitersPerMinute() const { return this->flow; }
        float usage24hLiters() const;
        int continuousFlowHours() const;
        bool leak() const;
        void persist();

    private:
        HAL* hal = nullptr;
        Settings* storage = nullptr;
        Logger* logger = nullptr;
        LedController* led = nullptr;

        struct Medium {
            const char* id;
            const char* label;       // settings choice
            const char* noun;        // Home Assistant entity names: "<noun> Meter", ...
            const char* title;       // OLED header, 4 chars
            const char* deviceClass; // HA device class of the total and the 24 h usage
            const char* icon;
            const char* leakClass;   // HA binary_sensor class of the continuous-flow flag
        };
        static const Medium MEDIA[];
        const Medium* medium = nullptr;
        float litersPerPulse = 1.0f;
        unsigned long minPulseGapMs = 50;
        int leakHours = 24;

        // Written by the ISR
        volatile unsigned long pendingPulses = 0;
        volatile unsigned long lastEdgeMs = 0;
        volatile unsigned long lastPulseMs = 0;
        volatile unsigned long previousPulseMs = 0;
        volatile bool anyPulse = false;

        double total = 0.0;
        double persistedTotal = 0.0;
        unsigned long pulseCount = 0;
        unsigned long lastPersistMs = 0;
        float flow = 0.0f;

        float hourLiters[USAGE_HOURS] = {};
        long hourSlot[USAGE_HOURS] = {};
        float barLiters[HISTORY_BARS] = {};
        long barSlot[HISTORY_BARS] = {};
        TrendBuffer flowTrend{60000UL};      // 56 x 1 min of flow rate
        RollingExtremes flowExtremes;        // 24 h low/high of flow rate

        void addLiters(double liters, unsigned long nowMs);
        float computeFlow(unsigned long nowMs) const;
        void applyMeterReading();

        static PulseMeterPlugin* instance;
        static IRAM_ATTR void pulseISR();
};

#endif
