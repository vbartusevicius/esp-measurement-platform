#ifndef ANALOG_DISTANCE_PLUGIN_H
#define ANALOG_DISTANCE_PLUGIN_H

#include "DistancePluginBase.h"
#include "Board.h"

class AnalogDistancePlugin : public DistancePluginBase
{
    public:
        static constexpr const char* PARAM_SENSOR_RANGE = "sensor_range";

    private:
        static constexpr int ANALOG_PIN = Board::ANALOG_PIN;
        static constexpr float SHUNT_OHMS = Board::MA_SHUNT_OHMS;
        static constexpr float VOLTAGE_REF = 3.3;
        static constexpr float MIN_CURRENT_MA = 4.0;
        static constexpr float MAX_CURRENT_MA = 20.0;
        // With an on-board shunt an open loop reads 0 mA, so the NAMUR NE43
        // limit applies; the legacy converter maps "no signal" to 4 mA.
        static constexpr float FAULT_CURRENT_MA = SHUNT_OHMS > 0.0f ? 3.6f : 4.17f;

        float sensorRange = 5.0f;

    protected:
        void setupPins() override;
        void loadPluginConfig() override;
        float readSensor() override;
        float computeRelative(float measured, float emptyDist, float fullDist) const override;
        float computeAbsolute(float measured, float emptyDist, float fullDist) const override;
        void addPluginParameterDefs(std::vector<ParameterDef>& defs) const override;
        const char* getDeviceName() const override;

    public:
        const char* getId() const override;
        const char* getName() const override;

        void publishHomeAssistantAutoconfig(MQTTClient& client, const HaDiscoveryContext& ctx) override;
};

#endif
