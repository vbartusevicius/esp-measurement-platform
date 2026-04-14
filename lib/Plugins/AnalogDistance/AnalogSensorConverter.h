#ifndef ANALOG_SENSOR_CONVERTER_H
#define ANALOG_SENSOR_CONVERTER_H

class AnalogSensorConverter
{
    public:
        static float voltageToCurrentMA(float voltage, float vRef, float minCurrentMA, float maxCurrentMA);
        static float currentToDistance(float currentMA, float minCurrentMA, float maxCurrentMA, float sensorRange);
        static bool isSensorConnected(float currentMA, float faultCurrentMA);
};

#endif
