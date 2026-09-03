#include "RadiationCalculator.h"

RadiationCalculator::RadiationCalculator()
    : cpm(0), dose(0.0f), doseAvg5m(0.0f), spanPointer(0)
{
}

void RadiationCalculator::calculate(int clicks, float tubeFactor, float deadTimeUs)
{
    this->calcBuffer.push_back(clicks);

    if ((int)this->calcBuffer.size() > CALCULATOR_BUFFER_SIZE) {
        this->calcBuffer.erase(this->calcBuffer.begin());
    }

    int totalClicks = 0;
    for (auto& v : this->calcBuffer) totalClicks += v;

    // Dead-time (saturation) correction: at high count rates the GM tube
    // misses pulses while recovering. Paralyzable model: m = n / (1 - n * tau).
    // Only applied when the observed rate stays below 90% of 1/tau.
    float correctedCpm = (float)totalClicks;
    if (deadTimeUs > 0) {
        float cps = totalClicks / 60.0f;
        float tau = deadTimeUs / 1000000.0f;
        if (cps * tau < 0.9f) {
            correctedCpm = 60.0f * cps / (1.0f - cps * tau);
        }
    }

    this->cpm = (int)(correctedCpm + 0.5f);
    this->dose = correctedCpm / tubeFactor;

    this->avgBuffer.push_back(this->dose);
    if ((int)this->avgBuffer.size() > AVG_BUFFER_SIZE) {
        this->avgBuffer.erase(this->avgBuffer.begin());
    }
    float sum = 0.0f;
    for (auto& v : this->avgBuffer) sum += v;
    this->doseAvg5m = sum / this->avgBuffer.size();
}

void RadiationCalculator::aggregateGraph(int spanSize)
{
    this->spanPointer++;

    this->spanBuffer.push_back(this->dose);
    if ((int)this->spanBuffer.size() > spanSize) {
        this->spanBuffer.erase(this->spanBuffer.begin());
    }

    if (this->spanPointer < spanSize) return;
    this->spanPointer = 0;

    // Calculate span average and add to graph buffer
    float sum = 0.0f;
    for (auto& v : this->spanBuffer) sum += v;
    float spanDose = sum / this->spanBuffer.size();

    this->graphBuffer.push_back(spanDose);
    if ((int)this->graphBuffer.size() > GRAPH_BUFFER_SIZE) {
        this->graphBuffer.erase(this->graphBuffer.begin());
    }
}

void RadiationCalculator::reset()
{
    this->calcBuffer.clear();
    this->spanBuffer.clear();
    this->graphBuffer.clear();
    this->avgBuffer.clear();
    this->cpm = 0;
    this->dose = 0.0f;
    this->doseAvg5m = 0.0f;
    this->spanPointer = 0;
}

int RadiationCalculator::getCPM() const
{
    return this->cpm;
}

float RadiationCalculator::getDose() const
{
    return this->dose;
}

float RadiationCalculator::getDoseAvg5m() const
{
    return this->doseAvg5m;
}

const std::vector<float>& RadiationCalculator::getGraphData() const
{
    return this->graphBuffer;
}

const std::vector<float>& RadiationCalculator::getSpanData() const
{
    return this->spanBuffer;
}

int RadiationCalculator::getSpanPointer() const
{
    return this->spanPointer;
}
