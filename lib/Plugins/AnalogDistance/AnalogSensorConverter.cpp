#include "AnalogSensorConverter.h"

float AnalogSensorConverter::voltageToCurrentMA(float voltage, float vRef, float minCurrentMA, float maxCurrentMA)
{
    return minCurrentMA + (voltage / vRef) * (maxCurrentMA - minCurrentMA);
}

float AnalogSensorConverter::currentToDistance(float currentMA, float minCurrentMA, float maxCurrentMA, float sensorRange)
{
    return ((currentMA - minCurrentMA) / (maxCurrentMA - minCurrentMA)) * sensorRange;
}

bool AnalogSensorConverter::isSensorConnected(float currentMA, float faultCurrentMA)
{
    return currentMA >= faultCurrentMA;
}
