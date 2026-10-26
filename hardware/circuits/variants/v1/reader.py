"""V1 optical dial reader (accessory board, ordered separately, not on the panel):
a pulse emitter for any mechanical meter whose dial has a reflective (metal)
half-disc or pointer under flat glass - water, gas, oil. 31.5 x 18 mm, held in
the rotatable carrier of a printed housing that locks onto the dial's hooks
(first fitted to a B METERS GMDM dial).

A Vishay TCRT5000 on the back looks through the dial glass at the half-metal
wheel. A TI LMV331 comparator with ~80 mV hysteresis compares the
phototransistor's emitter voltage (4.7k load) with a trimmer threshold and
drives the cable's pulse wire open-collector, like the IWM-PL3, so the main
unit's IO4 (4.7k pull-up to 3.3 V, 330R, BAT54S clamp) counts one falling edge
per wheel turn. A red LED (on while the output is low) shows the switching
point for setting the trimmer; its 1k feed also pulls the output up locally
(to <= 3.3 V, so IO4 is never driven above its rail).

J1 (WAGO 2059-303 SMD push-in, 2.7 mm tall, wire entry towards the cable hole, to the main unit's sensor bank):
  1 = +5V   (pole 1)
  2 = GND   (pole 9 or 10)
  3 = PULSE (pole 8, IO4)
"""

from common import block, part, power, power_flag, src
from skidl import Net

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"


def res(value, source):
    return part("Device", "R", value, R0603, src(source=source))


def cap(value, source):
    return part("Device", "C", value, C0603, src(source=source))


def build():
    gnd = power("GND")
    power_flag(gnd)
    v5_in, v5 = Net("+5V_IN"), Net("+5V_S")
    ir_a, sense, sense_in, thr = Net("IR_A"), Net("SENSE"), Net("SENSE_IN"), Net("THRESHOLD")
    cmp_out, led_a, pulse = Net("CMP_OUT"), Net("LED_A"), Net("PULSE")
    power_flag(v5_in)
    power_flag(v5)

    block("connector")
    j1 = part("Connector", "Screw_Terminal_01x03", "2059-303/998-403", "gateway_fp:TerminalBlock_WAGO_2059-303_SMD",
              src(mpn="2059-303/998-403", mfr="WAGO", lcsc="C3309252",
                  source="3-pole 3 mm SMD push-in terminal (0.14-0.34 mm2 solid) to the main unit: 1=+5V, 2=GND, 3=PULSE (IO4)"),
              ref="J1")
    j1[1] += v5_in
    j1[2] += gnd
    j1[3] += pulse

    block("power")
    d1 = part("Device", "D_Schottky", "B5819W", "Diode_SMD:D_SOD-123",
              src(mpn="B5819W SL", mfr="Jiangsu Changjing", lcsc="C8598",
                  source="Reverse-polarity protection: a swapped +5V/GND cable can't reach the comparator"),
              ref="D1")
    d1["A"] += v5_in
    d1["K"] += v5
    for value in ("10u 10V", "100n 50V"):
        c = cap(value, "+5V_S decoupling")
        c[1] += v5
        c[2] += gnd

    block("sensor")
    u1 = part("Sensor_Proximity", "CNY70", "TCRT5000", "gateway_fp:Vishay_TCRT5000_Clips",
              src(mpn="TCRT5000", mfr="Vishay", lcsc="C2984661",
                  source="Reflective IR sensor (950 nm, peak at 2.5 mm, 0.2-15 mm range) on the back, looking at the metallic half-disc through the dial glass"),
              ref="U1")
    r_ir = res("220R", "TCRT5000 emitter: (4.7 V - 1.2 V) / 220R = 16 mA (60 mA max)")
    r_ir[1] += v5
    r_ir[2] += ir_a
    u1["A"] += ir_a
    u1["K"] += gnd
    u1["C"] += v5
    u1["E"] += sense
    r_load = res("4k7", "Phototransistor emitter load: 0.2-0.9 mA -> 0.9-4.2 V")
    r_load[1] += sense
    r_load[2] += gnd
    c_sense = cap("100n 50V", "Sense low-pass (0.47 ms; at Q4 a wheel turn takes > 0.1 s)")
    c_sense[1] += sense
    c_sense[2] += gnd

    block("comparator")
    r_in = res("10k", "Comparator input resistor (hysteresis divider with the 390k)")
    r_in[1] += sense
    r_in[2] += sense_in
    r_hys = res("390k", "Positive feedback: ~3.2 V x 10k / 400k = 80 mV hysteresis")
    r_hys[1] += cmp_out
    r_hys[2] += sense_in
    rv1 = part("Device", "R_Potentiometer_Trim", "10k", "Potentiometer_SMD:Potentiometer_Bourns_TC33X_Vertical",
               src(mpn="TC33X-2-103E", mfr="Bourns", lcsc="C719176",
                   source="Threshold trimmer (0-4.7 V), adjusted through the lid"),
               ref="RV1")
    rv1[1] += v5
    rv1[3] += gnd
    rv1[2] += thr
    c_thr = cap("100n 50V", "Threshold filter")
    c_thr[1] += thr
    c_thr[2] += gnd
    u2 = part("Comparator", "LMV331", "LMV331", "Package_TO_SOT_SMD:SOT-23-5",
              src(mpn="LMV331IDBVR", mfr="Texas Instruments", lcsc="C34731",
                  source="Open-collector comparator, 2.7-5.5 V, 60 uA"),
              ref="U2")
    u2["+"] += sense_in
    u2["-"] += thr
    u2["V+"] += v5
    u2["V-"] += gnd
    u2[4] += cmp_out

    block("output")
    r_led = res("1k", "Indicator LED feed (~3 mA) and local output pull-up")
    r_led[1] += v5
    r_led[2] += led_a
    d2 = part("Device", "LED", "red", "LED_SMD:LED_0805_2012Metric",
              src(mpn="NCD0805R1", mfr="Foshan NationStar", lcsc="C84256",
                  source="Red indicator, on while the output is low: set the trimmer so it blinks once per wheel turn"),
              ref="D2")
    d2["A"] += led_a
    d2["K"] += cmp_out
    r_out = res("330R", "Output series resistor (cable ESD / short protection)")
    r_out[1] += cmp_out
    r_out[2] += pulse


NET_CLASSES = {
    "SELV": ["GND", "IR_A", "SENSE", "SENSE_IN", "THRESHOLD", "CMP_OUT", "LED_A", "PULSE", "Net-*"],
    "SELV-Power": ["+5V_IN", "+5V_S"],
}
