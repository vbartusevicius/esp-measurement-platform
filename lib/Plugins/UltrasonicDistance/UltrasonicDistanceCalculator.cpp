#include "UltrasonicDistanceCalculator.h"

float UltrasonicDistanceCalculator::getAbsolute(float distance, float emptyDist)
{
    float absolute = emptyDist - distance;
    return (absolute < 0) ? 0.0f : absolute;
}

float UltrasonicDistanceCalculator::getRelative(float distance, float emptyDist, float fullDist)
{
    float denominator = emptyDist - fullDist;
    if (denominator == 0) return 0.0f;
    return getAbsolute(distance, emptyDist) / denominator;
}
