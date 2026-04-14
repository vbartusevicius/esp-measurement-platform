#ifndef ULTRASONIC_DISTANCE_CALCULATOR_H
#define ULTRASONIC_DISTANCE_CALCULATOR_H

#include <vector>
#include <cmath>

class UltrasonicDistanceCalculator
{
    private:
        std::vector<float> buffer;

    public:
        float aggregate(float value, int windowSize, int maxDeltaPercent);
        float calculateAverage() const;
        void reset();
        const std::vector<float>& getBuffer() const;

        static float getAbsolute(float distance, float emptyDist);
        static float getRelative(float distance, float emptyDist, float fullDist);
};

#endif
