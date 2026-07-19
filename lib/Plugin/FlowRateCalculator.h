#ifndef FLOW_RATE_CALCULATOR_H
#define FLOW_RATE_CALCULATOR_H

#include <vector>

class FlowRateCalculator
{
    private:
        static const unsigned long WINDOW_MS = 60000;
        static const size_t MAX_SAMPLES = 120;

        struct Sample {
            float rate = 0.0;
            unsigned long time = 0;
        };

        std::vector<Sample> samples;
        float previousVolume = 0.0;
        unsigned long previousTime = 0;
        bool initialized;
        float currentRate;

    public:
        FlowRateCalculator();
        void reset();

        float update(float volumeLiters, unsigned long now);

        float getRate() const;
};

#endif
