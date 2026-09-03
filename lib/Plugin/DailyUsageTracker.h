#ifndef DAILY_USAGE_TRACKER_H
#define DAILY_USAGE_TRACKER_H

// Tracks consumption over a rolling 24-hour window using 24 hourly buckets.
// Consumption = sum of positive decreases in the measured volume.
class DailyUsageTracker
{
    public:
        DailyUsageTracker();

        void reset();
        // Updates with the current volume (liters). Decreases between calls
        // are accumulated into the current hour bucket; increases (refill)
        // are ignored.
        void update(float volumeLiters, unsigned long nowMs);
        float getUsageLiters() const;

    private:
        static const int HOURS = 24;
        static constexpr unsigned long HOUR_MS = 3600000UL;

        float buckets[HOURS];
        long bucketHour[HOURS];
        float previousVolume;
        bool initialized;
};

#endif
