#ifndef ANALOG_VOLTAGE_PLUGIN_H
#define ANALOG_VOLTAGE_PLUGIN_H

#include <vector>
#include "Board.h"
#include "IMqttContributor.h"
#include "IPlugin.h"
#include "RollingExtremes.h"
#include "TrendBuffer.h"

// Pressure (or any linear voltage) sensor on the 0-10 V input.
class AnalogVoltagePlugin : public IPlugin, public IMqttContributor
{
    public:
        static constexpr const char* PARAM_VOLTAGE_MIN = "voltage_min";
        static constexpr const char* PARAM_VOLTAGE_MAX = "voltage_max";
        static constexpr const char* PARAM_VALUE_MIN = "value_min";
        static constexpr const char* PARAM_VALUE_MAX = "value_max";
        static constexpr const char* PARAM_VALUE_UNIT = "value_unit";
        static constexpr const char* PARAM_DECIMALS = "value_decimals";
        static constexpr const char* PARAM_TITLE = "display_title";
        static constexpr const char* PARAM_SAMPLING_INTERVAL = "sampling_interval";

        static constexpr int INPUT_PIN = Board::V0_10_PIN;
        static constexpr float DIVIDER = Board::V0_10_DIVIDER;
        static constexpr int OVERSAMPLE = 16;

    private:
        HAL* hal = nullptr;
        Settings* storage = nullptr;
        Logger* logger = nullptr;

        float voltageMin = 0.5f;
        float voltageMax = 4.5f;
        float valueMin = 0.0f;
        float valueMax = 10.0f;
        String unit = "bar";
        String title = "PRES";
        int decimals = 1;
        int samplingIntervalSec = 5;

        float inputVolts = 0.0f;
        float value = 0.0f;
        bool sensorConnected = false;
        bool sampled = false;
        TrendBuffer trend{60000UL};
        RollingExtremes extremes;
        TrendBuffer history{900000UL, 96};   // 24 h, 15 min points (web history)

    public:
        const char* getId() const override;
        const char* getName() const override;
        uint8_t inputs() const override { return Board::INPUT_V; }

        void setup(HAL* hal, Settings* storage, Logger* logger, LedController* led) override;
        void loop() override;

        void getParameterDefs(std::vector<ParameterDef>& defs) const override;
        void getStats(std::vector<StatEntry>& entries) const override;
        bool getScreen(ScreenModel& model) const override;
        bool getChartData(std::vector<float>& points, int& spanSeconds) const override;
        int getSamplingInterval() const override { return this->samplingIntervalSec; }

        void publishMqtt(MQTTClient& client, const String& baseTopic) override;
        void publishHomeAssistantAutoconfig(MQTTClient& client, const HaDiscoveryContext& ctx) override;

        IMqttContributor* mqtt() override { return this; }
};

#endif
