#include "FlowRateCalculator.h"

FlowRateCalculator::FlowRateCalculator()
{
    this->reset();
}

void FlowRateCalculator::reset()
{
    this->samples.clear();
    this->previousVolume = 0;
    this->previousTime = 0;
    this->initialized = false;
    this->currentRate = 0;
}

float FlowRateCalculator::update(float volumeLiters, unsigned long now)
{
    if (!this->initialized) {
        this->previousVolume = volumeLiters;
        this->previousTime = now;
        this->initialized = true;
        this->currentRate = 0;
        return 0;
    }

    float deltaMinutes = (now - this->previousTime) / 60000.0f;
    if (deltaMinutes > 0) {
        float instantRate = (volumeLiters - this->previousVolume) / deltaMinutes;
        this->samples.push_back({instantRate, now});
    }

    // Enforce maximum sample limit to prevent memory issues
    if (this->samples.size() > MAX_SAMPLES) {
        this->samples.erase(this->samples.begin());
    }

    this->previousVolume = volumeLiters;
    this->previousTime = now;

    // Remove samples older than the moving average window
    while (!this->samples.empty() && (now - this->samples.front().time) > WINDOW_MS) {
        this->samples.erase(this->samples.begin());
    }

    // Calculate moving average
    if (this->samples.empty()) {
        this->currentRate = 0;
    } else {
        float sum = 0;
        for (auto& s : this->samples) {
            sum += s.rate;
        }
        this->currentRate = sum / this->samples.size();
    }

    return this->currentRate;
}

float FlowRateCalculator::getRate() const
{
    return this->currentRate;
}
