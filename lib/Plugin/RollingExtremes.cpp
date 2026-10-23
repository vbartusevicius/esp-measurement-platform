#include "RollingExtremes.h"

void RollingExtremes::update(float value, unsigned long nowMs)
{
    long slot = (long)(nowMs / this->bucketMs);
    Bucket& bucket = this->buckets[slot % BUCKETS];
    if (bucket.slot != slot) {
        bucket.slot = slot;
        bucket.low = value;
        bucket.high = value;
    } else {
        if (value < bucket.low) bucket.low = value;
        if (value > bucket.high) bucket.high = value;
    }
    this->currentSlot = slot;
}

void RollingExtremes::reset()
{
    for (auto& bucket : this->buckets) bucket.slot = -1;
    this->currentSlot = -1;
}

bool RollingExtremes::live(const Bucket& bucket) const
{
    return bucket.slot >= 0 && bucket.slot <= this->currentSlot && bucket.slot > this->currentSlot - BUCKETS;
}

bool RollingExtremes::valid() const
{
    return this->currentSlot >= 0;
}

float RollingExtremes::min() const
{
    bool found = false;
    float result = 0.0f;
    for (const auto& bucket : this->buckets) {
        if (!this->live(bucket)) continue;
        if (!found || bucket.low < result) result = bucket.low;
        found = true;
    }
    return result;
}

float RollingExtremes::max() const
{
    bool found = false;
    float result = 0.0f;
    for (const auto& bucket : this->buckets) {
        if (!this->live(bucket)) continue;
        if (!found || bucket.high > result) result = bucket.high;
        found = true;
    }
    return result;
}
