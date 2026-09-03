#ifndef ULTRASONIC_DISTANCE_PLUGIN_H
#define ULTRASONIC_DISTANCE_PLUGIN_H

#include "DistancePluginBase.h"

class UltrasonicDistancePlugin : public DistancePluginBase
{
    private:
        static constexpr int TRIG_PIN = D1;
        static constexpr int ECHO_PIN = D2;
        static constexpr float ABSOLUTE_TEMP = 273.16;
        static constexpr float CURRENT_TEMP = 15.0;

        double speedOfSound = 0.0;

    public:
        void setup(HAL* hal, Storage* storage, Logger* logger, LedController* led) override;

    protected:
        void setupPins() override;
        float readSensor() override;
        float computeRelative(float measured, float emptyDist, float fullDist) const override;
        float computeAbsolute(float measured, float emptyDist, float fullDist) const override;
        void addPluginParameterDefs(std::vector<ParameterDef>& defs) const override;
        const char* getDeviceName() const override;

    public:
        const char* getId() const override;
        const char* getName() const override;

        void publishHomeAssistantAutoconfig(MQTTClient& client, const String& deviceId, const String& stateTopic) override;
};

#endif
