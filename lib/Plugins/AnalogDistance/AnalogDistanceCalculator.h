#ifndef ANALOG_DISTANCE_CALCULATOR_H
#define ANALOG_DISTANCE_CALCULATOR_H

// Static math for a 4-20mA analog sensor: measured value rises with level,
// so relative fill is (measured - empty) / (full - empty).
class AnalogDistanceCalculator
{
    public:
        static float getRelative(float sensorDistance, float emptyDist, float fullDist);
        static float getAbsolute(float sensorDistance, float emptyDist, float fullDist);
};

#endif
