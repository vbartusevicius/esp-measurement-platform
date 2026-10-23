#ifndef ANALOG_SENSOR_CONVERTER_H
#define ANALOG_SENSOR_CONVERTER_H

class AnalogSensorConverter
{
    public:
        static float shuntMillivoltsToCurrentMA(int millivolts, float shuntOhms);
        static float currentToDistance(float currentMA, float minCurrentMA, float maxCurrentMA, float sensorRange);
        static bool isSensorConnected(float currentMA, float faultCurrentMA);
};

#endif
