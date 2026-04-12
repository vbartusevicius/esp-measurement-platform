#ifndef ANALOG_DISTANCE_PLUGIN_H
#define ANALOG_DISTANCE_PLUGIN_H

#include "IPlugin.h"
#include "Storage.h"
#include "Logger.h"
#include "LedController.h"
#include <vector>

class AnalogDistancePlugin : public IPlugin
{
    public:
        static constexpr const char* PARAM_DISTANCE_EMPTY = "distance_empty";
        static constexpr const char* PARAM_DISTANCE_FULL = "distance_full";
        static constexpr const char* PARAM_SENSOR_RANGE = "sensor_range";
        static constexpr const char* PARAM_AVG_SAMPLE_COUNT = "avg_sample_count";
        static constexpr const char* PARAM_SAMPLING_INTERVAL = "sampling_interval";
        static constexpr const char* PARAM_MAX_DELTA = "max_distance_delta";

    private:
        static constexpr int ANALOG_PIN = A0;
        static constexpr float VOLTAGE_REF = 3.3;
        static constexpr float MIN_CURRENT_MA = 4.0;
        static constexpr float MAX_CURRENT_MA = 20.0;
        static constexpr float FAULT_CURRENT_MA = 4.17;

        Storage* storage;
        Logger* logger;

        std::vector<float> avgBuffer;
        float measuredDistance;
        float relativeDistance;
        float absoluteDistance;
        bool sensorConnected;

        float readSensor();
        bool isSensorConnected(float voltage);
        float voltageToDistance(float voltage);
        float voltageToCurrentMA(float voltage);
        float getRelative(float distance);
        float getAbsolute(float distance);
        float aggregate(float value);
        float calculateAverage();

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

        int getSamplingInterval() const override;
};

#endif
