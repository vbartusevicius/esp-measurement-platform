#include "MovingAverageFilter.h"
#include <cmath>

float MovingAverageFilter::aggregate(float value, int windowSize, int maxDeltaPercent)
{
    float lastValue = this->buffer.empty() ? 0.0f : this->buffer.back();

    if ((int)this->buffer.size() >= windowSize) {
        this->buffer.erase(this->buffer.begin());
    }

    float diff = std::abs(lastValue - value);
    bool deltaOK = value * (maxDeltaPercent / 100.0f) > diff || this->buffer.empty();
    bool valueOK = std::round(value * 100.0f) > 0;

    if (deltaOK && valueOK) {
        this->buffer.push_back(value);
    }

    return this->calculateAverage();
}

float MovingAverageFilter::calculateAverage() const
{
    if (this->buffer.empty()) return 0.0f;
    float sum = 0.0f;
    for (auto& v : this->buffer) sum += v;
    return sum / this->buffer.size();
}

void MovingAverageFilter::reset()
{
    this->buffer.clear();
}

const std::vector<float>& MovingAverageFilter::getBuffer() const
{
    return this->buffer;
}
