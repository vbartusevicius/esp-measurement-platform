"""24 V DC input protection + loop power pass-through + SCT2400 5 V 600 mA buck converter.

Input range: 9-30 V DC (nominal 24 V DC).
  J1 pin 1 (VIN_RAW) -> F1 (1.1 A 33 V 1812 PTC resettable fuse) -> VIN_FUSED
  D1 (SMAJ33A unidirectional TVS across VIN_FUSED..GND) clamps surges
  D2 (SS16 60 V 1 A Schottky diode) blocks reverse polarity -> +24V_LOOP
  +24V_LOOP feeds both the top sensor terminal J2 pin 1 (for 2-wire 4-20 mA
  transmitters like SWK-LT100) and the SCT2400 5 V 600 mA step-down converter.
"""

from common import block, part, power_flag, src
from skidl import Net

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
SMA = "Diode_SMD:D_SMA"
FUSE_1812 = "Fuse:Fuse_1812_4532Metric"
TSOT23_6 = "Package_TO_SOT_SMD:TSOT-23-6"


def res(value, fields=None, footprint=R0603):
    return part("Device", "R", value, footprint, fields)


def cap(value, fields=None, footprint=C0603):
    return part("Device", "C", value, footprint, fields)


def build(gnd):
    vin_raw = Net("VIN_RAW")
    vin_fused = Net("VIN_FUSED")
    v24_loop = Net("+24V_LOOP")
    v5 = Net("+5V")
    sw = Net("BUCK5_SW")

    block("pwr_in")
    f1 = part("Device", "Polyfuse", "1.1A", FUSE_1812,
              src(mpn="1812L110/33MR", mfr="Littelfuse", lcsc="C142747",
                  source="1.1 A hold / 2.2 A trip 33 V 1812 PTC resettable fuse on 24 V input"),
              ref="F1")
    f1[1] += vin_raw
    f1[2] += vin_fused

    d2 = part("Device", "D_Schottky", "SS34", SMA,
              src(mpn="SS34", mfr="MDD", lcsc="C8678",
                  source="40 V 3 A reverse-polarity blocking Schottky diode (JLCPCB Basic Part)"),
              ref="D2")
    d2["A"] += vin_fused
    d2["K"] += v24_loop
    power_flag(v24_loop)

    d1 = part("Device", "D_Zener", "SMAJ33A", SMA,
              src(mpn="SMAJ33A", mfr="Littelfuse", lcsc="C113966",
                  source="33 V unidirectional TVS surge suppressor after reverse diode"),
              ref="D1")
    d1["A"] += gnd
    d1["K"] += v24_loop

    # --- 24 V -> 5 V 600 mA synchronous buck (SCT2400TVBR, 4.5-40 V input) ---
    block("buck5v")
    u1 = part("gateway", "SCT2400", "SCT2400TVBR", TSOT23_6,
              src(mpn="SCT2400TVBR", mfr="SCT", lcsc="C2693819",
                  source="SCT2400 datasheet: 4.5-40 V in, 600 mA, 2 MHz step-down converter"),
              ref="U1")
    u1["VIN"] += v24_loop
    u1["GND"] += gnd

    # UVLO divider: 100k / 20k -> turn-on at ~7.3 V (supports both 12 V and 24 V supplies)
    r_en_top = res("100k", src(source="SCT2400 EN UVLO top"))
    r_en_top[1] += v24_loop
    r_en_top[2] += u1["EN"]
    r_en_bot = res("20k", src(source="SCT2400 EN UVLO bottom"))
    r_en_bot[1] += u1["EN"]
    r_en_bot[2] += gnd

    c_bst = cap("100n 50V", src(source="SCT2400 BST bootstrap cap"))
    c_bst[1] += u1["BST"]
    c_bst[2] += sw
    sw += u1["SW"]

    l1 = part("Device", "L", "4.7uH", "Inductor_SMD:L_APV_ANR4012",
              src(mpn="SMNR4012-4R7MT", mfr="Sunna", lcsc="C135248",
                  source="SCT2400 4.7 uH 1.15 A shielded power inductor 4x4 mm"),
              ref="L1")
    l1[1] += sw
    l1[2] += v5
    power_flag(v5)

    # FB divider: VOUT = 0.81 V * (1 + 51k / 10k) = 4.94 V
    r_fb_top = res("51k", src(source="SCT2400 FB top: 4.94 V output"))
    r_fb_top[1] += v5
    r_fb_top[2] += u1["FB"]
    r_fb_bot = res("10k", src(source="SCT2400 FB bottom"))
    r_fb_bot[1] += u1["FB"]
    r_fb_bot[2] += gnd

    for _ in range(2):
        c_in = cap("10u 50V", src(source="SCT2400 24 V input decoupling"), footprint=C0805)
        c_in[1] += v24_loop
        c_in[2] += gnd
    c_in_hf = cap("100n 50V", src(source="SCT2400 HF input decoupling"))
    c_in_hf[1] += v24_loop
    c_in_hf[2] += gnd

    for val in ("22u 25V", "22u 25V", "100n 50V"):
        c_out = cap(val, src(source="SCT2400 5 V output decoupling"),
                    footprint=C0805 if "22u" in val else C0603)
        c_out[1] += v5
        c_out[2] += gnd

    return {"vin_raw": vin_raw, "v24_loop": v24_loop, "v5": v5}
