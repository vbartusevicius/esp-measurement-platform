#include "DailyUsageTracker.h"

DailyUsageTracker::DailyUsageTracker()
{
    this->reset();
}

void DailyUsageTracker::reset()
{
    for (int i = 0; i < HOURS; i++) {
        this->buckets[i] = 0.0f;
        this->bucketHour[i] = -1;
    }
    this->previousVolume = 0.0f;
    this->initialized = false;
}

void DailyUsageTracker::update(float volumeLiters, unsigned long nowMs)
{
    if (!this->initialized) {
        this->previousVolume = volumeLiters;
        this->initialized = true;
        return;
    }

    float used = this->previousVolume - volumeLiters;
    this->previousVolume = volumeLiters;

    long hour = (long)(nowMs / HOUR_MS);

    // Sweep-expire buckets older than the 24h window
    for (int i = 0; i < HOURS; i++) {
        if (this->bucketHour[i] != hour && (this->bucketHour[i] < 0 || hour - this->bucketHour[i] >= HOURS)) {
            this->buckets[i] = 0.0f;
        }
    }

    if (used <= 0) return;  // refill or no change

    int idx = (int)(hour % HOURS);
    if (this->bucketHour[idx] != hour) {
        this->buckets[idx] = 0.0f;
        this->bucketHour[idx] = hour;
    }
    this->buckets[idx] += used;
}

float DailyUsageTracker::getUsageLiters() const
{
    float sum = 0.0f;
    for (int i = 0; i < HOURS; i++) sum += this->buckets[i];
    return sum;
}
