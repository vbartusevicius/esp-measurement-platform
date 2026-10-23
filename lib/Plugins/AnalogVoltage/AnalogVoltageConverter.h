#ifndef ANALOG_VOLTAGE_CONVERTER_H
#define ANALOG_VOLTAGE_CONVERTER_H

// Voltage-output sensors on the 0-10 V input (J2.5, 22k/10k divider):
// 0.5-4.5 V ratiometric pressure transducers, 0-5 V and 0-10 V sensors.
class AnalogVoltageConverter
{
    public:
        static float pinToInputVolts(int pinMillivolts, float dividerRatio);

        // Linear map of [vMin, vMax] onto [outMin, outMax], clamped to the range.
        static float scale(float volts, float vMin, float vMax, float outMin, float outMax);

        // Live-zero sensors (vMin >= 0.3 V, e.g. 0.5-4.5 V) read ~0 V when the
        // wire is open or the sensor unpowered, and rail voltage when shorted.
        // Plain 0-x V sensors can only be checked for over-range.
        static bool isConnected(float volts, float vMin, float vMax);
};

#endif
