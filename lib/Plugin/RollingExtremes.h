#ifndef ROLLING_EXTREMES_H
#define ROLLING_EXTREMES_H

// Lowest/highest value over a sliding window (default 24 h) kept as 24
// min/max buckets, so memory stays constant whatever the sample rate.
class RollingExtremes
{
    public:
        static constexpr int BUCKETS = 24;

        explicit RollingExtremes(unsigned long bucketMs = 3600000UL) : bucketMs(bucketMs) {}

        void update(float value, unsigned long nowMs);
        void reset();
        bool valid() const;
        float min() const;
        float max() const;

    private:
        struct Bucket {
            long slot = -1;
            float low = 0.0f;
            float high = 0.0f;
        };

        Bucket buckets[BUCKETS];
        unsigned long bucketMs;
        long currentSlot = -1;

        bool live(const Bucket& bucket) const;
};

#endif
