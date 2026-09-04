#include "LevelFilter.h"
#include <algorithm>
#include <cmath>

LevelFilter::LevelFilter()
{
    this->reset();
}

void LevelFilter::reset()
{
    this->window.clear();
    this->output = 0.0f;
    this->lastMedian = 0.0f;
    this->pendingStepCount = 0;
    this->lastMs = 0;
    this->initialized = false;
}

bool LevelFilter::hasValue() const
{
    return this->initialized;
}

float LevelFilter::getFiltered() const
{
    return this->output;
}

float LevelFilter::median() const
{
    if (this->window.empty()) return this->lastMedian;

    std::vector<float> sorted(this->window);
    std::sort(sorted.begin(), sorted.end());
    size_t n = sorted.size();
    return (n % 2 == 1) ? sorted[n / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0f;
}

float LevelFilter::process(float value, int windowSize, float deadband,
                           int snapAfterSamples, float maxRatePerMin, unsigned long nowMs)
{
    // Stage 1: validity gate - timeouts (0 / near-0) are discarded silently
    if (std::round(value * 100.0f) <= 0) return this->output;

    // Stage 2: median window
    this->window.push_back(value);
    if ((int)this->window.size() > windowSize) {
        this->window.erase(this->window.begin());
    }
    this->lastMedian = this->median();

    if (!this->initialized) {
        this->output = this->lastMedian;
        this->initialized = true;
        this->lastMs = nowMs;
        return this->output;
    }

    float diff = this->lastMedian - this->output;

    if (std::abs(diff) > deadband) {
        // Stage 3b: big step - hold until confirmed for snapAfterSamples
        this->pendingStepCount++;
        if (this->pendingStepCount >= snapAfterSamples && snapAfterSamples > 0) {
            this->output = this->lastMedian;
            this->pendingStepCount = 0;
        }
    } else {
        // Stage 3a: small change - pass through (optionally slew-limited)
        this->pendingStepCount = 0;
        if (maxRatePerMin > 0.0f && nowMs > this->lastMs) {
            float maxStep = maxRatePerMin * ((nowMs - this->lastMs) / 60000.0f);
            if (diff > maxStep) diff = maxStep;
            if (diff < -maxStep) diff = -maxStep;
        }
        this->output += diff;
    }

    this->lastMs = nowMs;
    return this->output;
}
