#ifndef MOVING_AVERAGE_FILTER_H
#define MOVING_AVERAGE_FILTER_H

#include <vector>

class MovingAverageFilter
{
    private:
        std::vector<float> buffer;

    public:
        // Adds a value to the rolling window, rejecting zeros and jumps
        // larger than maxDeltaPercent relative to the new value.
        float aggregate(float value, int windowSize, int maxDeltaPercent);
        float calculateAverage() const;
        void reset();
        const std::vector<float>& getBuffer() const;
};

#endif
