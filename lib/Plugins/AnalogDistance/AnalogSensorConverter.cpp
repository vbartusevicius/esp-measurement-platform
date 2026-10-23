#include "AnalogSensorConverter.h"

float AnalogSensorConverter::shuntMillivoltsToCurrentMA(int millivolts, float shuntOhms)
{
    if (shuntOhms <= 0.0f || millivolts <= 0) {
        return 0.0f;
    }
    return millivolts / shuntOhms;
}

float AnalogSensorConverter::currentToDistance(float currentMA, float minCurrentMA, float maxCurrentMA, float sensorRange)
{
    return ((currentMA - minCurrentMA) / (maxCurrentMA - minCurrentMA)) * sensorRange;
}

bool AnalogSensorConverter::isSensorConnected(float currentMA, float faultCurrentMA)
{
    return currentMA >= faultCurrentMA;
}
