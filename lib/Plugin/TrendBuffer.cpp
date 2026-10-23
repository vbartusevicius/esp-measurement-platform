#include "TrendBuffer.h"

void TrendBuffer::push(float value)
{
    if (this->count < this->buffer.size()) {
        this->buffer[(this->start + this->count) % this->buffer.size()] = value;
        this->count++;
    } else {
        this->buffer[this->start] = value;
        this->start = (this->start + 1) % this->buffer.size();
    }
}

void TrendBuffer::add(float value, unsigned long nowMs)
{
    if (this->bucketSamples > 0 && nowMs - this->bucketStart >= this->bucketMs) {
        this->push((float)(this->bucketSum / this->bucketSamples));
        this->bucketSum = 0.0;
        this->bucketSamples = 0;
    }
    if (this->bucketSamples == 0) this->bucketStart = nowMs;
    this->bucketSum += value;
    this->bucketSamples++;
}

void TrendBuffer::reset()
{
    this->start = 0;
    this->count = 0;
    this->bucketSum = 0.0;
    this->bucketSamples = 0;
}

std::vector<float> TrendBuffer::values() const
{
    std::vector<float> out;
    out.reserve(this->buffer.size());
    size_t skip = (this->bucketSamples > 0 && this->count == this->buffer.size()) ? 1 : 0;
    for (size_t i = skip; i < this->count; i++) {
        out.push_back(this->buffer[(this->start + i) % this->buffer.size()]);
    }
    if (this->bucketSamples > 0) out.push_back((float)(this->bucketSum / this->bucketSamples));
    return out;
}
