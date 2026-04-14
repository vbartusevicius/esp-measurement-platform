#ifndef ANALOG_DISTANCE_CALCULATOR_H
#define ANALOG_DISTANCE_CALCULATOR_H

#include <vector>
#include <cmath>

class AnalogDistanceCalculator
{
    private:
        std::vector<float> buffer;

    public:
        float aggregate(float value, int windowSize, int maxDeltaPercent);
        float calculateAverage() const;
        void reset();
        const std::vector<float>& getBuffer() const;

        static float getRelative(float sensorDistance, float emptyDist, float fullDist);
        static float getAbsolute(float sensorDistance, float emptyDist, float fullDist);
};

#endif
