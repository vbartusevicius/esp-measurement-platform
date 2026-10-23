#ifndef TREND_BUFFER_H
#define TREND_BUFFER_H

#include <cstddef>
#include <vector>

// Fixed-length history of bucket averages. Default 56 points = the 64 px OLED
// chart width minus its frame; the 24 h web history uses 96 x 15 min.
class TrendBuffer
{
    public:
        static constexpr size_t CAPACITY = 56;

        explicit TrendBuffer(unsigned long bucketMs = 60000UL, size_t capacity = CAPACITY)
            : buffer(capacity > 0 ? capacity : 1, 0.0f), bucketMs(bucketMs) {}

        void setBucketMs(unsigned long ms) { this->bucketMs = ms > 0 ? ms : 1; }
        unsigned long getBucketMs() const { return this->bucketMs; }
        void add(float value, unsigned long nowMs);
        void reset();

        // Completed buckets plus the running bucket, oldest first.
        std::vector<float> values() const;

    private:
        std::vector<float> buffer;
        size_t start = 0;
        size_t count = 0;
        unsigned long bucketMs;
        unsigned long bucketStart = 0;
        double bucketSum = 0.0;
        unsigned int bucketSamples = 0;

        void push(float value);
};

#endif
