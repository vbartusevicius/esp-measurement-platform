#ifndef RADIATION_CALCULATOR_H
#define RADIATION_CALCULATOR_H

#include <vector>

class RadiationCalculator
{
    private:
        static const int CALCULATOR_BUFFER_SIZE = 60;
        static const int GRAPH_BUFFER_SIZE = 128;

        std::vector<int> calcBuffer;
        int cpm;
        float dose;

        int spanPointer;
        std::vector<float> spanBuffer;
        std::vector<float> graphBuffer;

    public:
        RadiationCalculator();

        void calculate(int clicks, float tubeFactor);
        void aggregateGraph(int spanSize);
        void reset();

        int getCPM() const;
        float getDose() const;
        const std::vector<float>& getGraphData() const;
        const std::vector<float>& getSpanData() const;
        int getSpanPointer() const;
};

#endif
