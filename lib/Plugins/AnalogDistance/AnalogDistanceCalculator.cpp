#include "AnalogDistanceCalculator.h"

float AnalogDistanceCalculator::getRelative(float sensorDistance, float emptyDist, float fullDist)
{
    if (sensorDistance <= emptyDist) return 0.0;
    if (sensorDistance >= fullDist) return 1.0;
    return (sensorDistance - emptyDist) / (fullDist - emptyDist);
}

float AnalogDistanceCalculator::getAbsolute(float sensorDistance, float emptyDist, float fullDist)
{
    float relative = getRelative(sensorDistance, emptyDist, fullDist);
    return relative * fullDist;
}
