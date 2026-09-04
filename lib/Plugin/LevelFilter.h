#ifndef LEVEL_FILTER_H
#define LEVEL_FILTER_H

#include <vector>

// Three-stage distance/level filter:
//  1. Validity gate: sensor timeouts (0) are skipped without touching state.
//  2. Median of the last N valid readings kills spike noise (ultrasonic echo
//     outliers are bimodal junk, not Gaussian - median handles them far
//     better than averaging).
//  3. Step handling: changes within the deadband pass through immediately
//     (optionally slew-limited); changes beyond the deadband are held until
//     the median persists past it for snapAfterSamples cycles, then the
//     output snaps to the new level. This can never get stuck: real level
//     changes always win eventually.
class LevelFilter
{
    public:
        LevelFilter();

        void reset();

        // Samples are raw distances (meters). deadband in meters,
        // maxRatePerMin in meters/minute (0 = no slew limiting),
        // snapAfterSamples > 0. Returns the filtered level.
        float process(float value, int windowSize, float deadband,
                      int snapAfterSamples, float maxRatePerMin, unsigned long nowMs);

        float getFiltered() const;
        bool hasValue() const;

    private:
        std::vector<float> window;
        float output;
        float lastMedian;
        int pendingStepCount;
        unsigned long lastMs;
        bool initialized;

        float median() const;
};

#endif
