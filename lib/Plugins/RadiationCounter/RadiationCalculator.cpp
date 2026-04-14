#include "RadiationCalculator.h"

RadiationCalculator::RadiationCalculator()
    : cpm(0), dose(0.0f), spanPointer(0)
{
}

void RadiationCalculator::calculate(int clicks, float tubeFactor)
{
    this->calcBuffer.push_back(clicks);

    if ((int)this->calcBuffer.size() > CALCULATOR_BUFFER_SIZE) {
        this->calcBuffer.erase(this->calcBuffer.begin());
    }

    int totalClicks = 0;
    for (auto& v : this->calcBuffer) totalClicks += v;
    this->cpm = totalClicks;

    this->dose = this->cpm / tubeFactor;
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
    this->cpm = 0;
    this->dose = 0.0f;
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
