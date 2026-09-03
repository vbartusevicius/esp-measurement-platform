#ifndef ULTRASONIC_DISTANCE_CALCULATOR_H
#define ULTRASONIC_DISTANCE_CALCULATOR_H

// Static math for a top-mounted ultrasonic sensor: measured distance rises
// as the level drops, so absolute depth is emptyDist - distance.
class UltrasonicDistanceCalculator
{
    public:
        static float getAbsolute(float distance, float emptyDist);
        static float getRelative(float distance, float emptyDist, float fullDist);
};

#endif
