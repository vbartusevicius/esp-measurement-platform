#include "AnalogVoltageConverter.h"

float AnalogVoltageConverter::pinToInputVolts(int pinMillivolts, float dividerRatio)
{
    return (pinMillivolts / 1000.0f) * dividerRatio;
}

float AnalogVoltageConverter::scale(float volts, float vMin, float vMax, float outMin, float outMax)
{
    if (vMax <= vMin) return outMin;
    float ratio = (volts - vMin) / (vMax - vMin);
    if (ratio < 0.0f) ratio = 0.0f;
    if (ratio > 1.0f) ratio = 1.0f;
    return outMin + ratio * (outMax - outMin);
}

bool AnalogVoltageConverter::isConnected(float volts, float vMin, float vMax)
{
    float span = vMax - vMin;
    if (volts > vMax + span * 0.1f) return false;
    if (vMin >= 0.3f && volts < vMin * 0.5f) return false;
    return true;
}
