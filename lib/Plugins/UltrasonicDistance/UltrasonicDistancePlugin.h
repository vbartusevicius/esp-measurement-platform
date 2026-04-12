#ifndef ULTRASONIC_DISTANCE_PLUGIN_H
#define ULTRASONIC_DISTANCE_PLUGIN_H

#include "IPlugin.h"
#include "Storage.h"
#include "Logger.h"
#include "LedController.h"
#include <vector>

class UltrasonicDistancePlugin : public IPlugin
{
    public:
        static constexpr const char* PARAM_DISTANCE_EMPTY = "distance_empty";
        static constexpr const char* PARAM_DISTANCE_FULL = "distance_full";
        static constexpr const char* PARAM_AVG_SAMPLE_COUNT = "avg_sample_count";
        static constexpr const char* PARAM_SAMPLING_INTERVAL = "sampling_interval";
        static constexpr const char* PARAM_MAX_DELTA = "max_distance_delta";

    private:
        static constexpr int TRIG_PIN = D1;
        static constexpr int ECHO_PIN = D2;
        static constexpr float ABSOLUTE_TEMP = 273.16;
        static constexpr float CURRENT_TEMP = 15.0;

        Storage* storage;
        Logger* logger;
        double speedOfSound;

        std::vector<float> avgBuffer;
        float measuredDistance;
        float relativeDistance;
        float absoluteDistance;
        bool sensorConnected;

        float readSensor();
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
};

#endif
