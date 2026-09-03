#ifndef RADIATION_CALCULATOR_H
#define RADIATION_CALCULATOR_H

#include <vector>

class RadiationCalculator
{
    private:
        static const int CALCULATOR_BUFFER_SIZE = 60;
        static const int GRAPH_BUFFER_SIZE = 128;
        static const int AVG_BUFFER_SIZE = 300;  // 5 minutes of 1s samples

        std::vector<int> calcBuffer;
        int cpm;
        float dose;

        std::vector<float> avgBuffer;  // per-second dose values for the 5-min average
        float doseAvg5m;

        int spanPointer;
        std::vector<float> spanBuffer;
        std::vector<float> graphBuffer;

    public:
        RadiationCalculator();

        // clicks: counts in the last second. deadTimeUs: GM tube dead time
        // (paralyzable-model saturation correction, ~90us for J305; 0 = off).
        void calculate(int clicks, float tubeFactor, float deadTimeUs = 0.0f);
        void aggregateGraph(int spanSize);
        void reset();

        int getCPM() const;
        float getDose() const;
        float getDoseAvg5m() const;
        const std::vector<float>& getGraphData() const;
        const std::vector<float>& getSpanData() const;
        int getSpanPointer() const;
};

#endif
