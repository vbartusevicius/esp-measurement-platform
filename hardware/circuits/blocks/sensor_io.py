"""Universal protected sensor front-end + SMD changeover relay block:
  - 4-20 mA (J2 pin 4 -> XIAO D1 / GPIO1 / ADC1_CH1):
      Fixed 165.0 ohm shunt (330R || 330R: 4 mA = 0.66 V, 20 mA = 3.30 V),
      followed by 10k + 100nF hardware RC low-pass filter (fc = 159 Hz) and
      SS16 Schottky overvoltage clamp to +3V3. Zero jumpers required.
  - 0-10V / 0-5V (J2 pin 5 -> XIAO D0 / GPIO0 / ADC1_CH0):
      Precision 22k / 10k (10/32 = 0.3125) voltage divider to GND + 100nF
      filter cap + SS16 Schottky clamp to +3V3. Reads 0-10 V (0..3.125 V at ADC),
      2-10 V, 0-5 V, and 0.4-4.5 V ratiometric pressure sensors (150 PSI)
      purely via Web UI min/max voltage settings. Zero jumpers required.
  - IO1 (J2 pin 6: SDA / RX / Radiation PULSE) & IO2 (J2 pin 7: SCL / TX):
      Each has a 4.7k pull-up to +3V3, 330R series protection resistor, and
      SS16 Schottky clamp to +3V3.
  - SMD 3-Way Relay (J1 pins 3=NC, 4=COM, 5=NO):
      Omron G6K-2F-Y-TR DC5 (LCSC C47190, DPDT wired in parallel for 2x contact
      reliability), driven by BC847B NPN transistor Q1 + SS16 flyback diode.
"""

from common import block, part, src
from skidl import Net

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
SMA = "Diode_SMD:D_SMA"
SOD123 = "Diode_SMD:D_SOD-123"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
RELAY_G6S = "gateway_fp:Relay_DPDT_Omron_G6S-2F_2A"


def res(value, fields=None, footprint=R0603):
    return part("Device", "R", value, footprint, fields)


def cap(value, fields=None, footprint=C0603):
    return part("Device", "C", value, footprint, fields)


def build(gnd, v3, v5):
    ma_term = Net("MA_TERM")
    ma_mcu = Net("MA_MCU")
    v0_10_term = Net("V0_10_TERM")
    v0_10_mcu = Net("V0_10_MCU")

    # --- 1. Dedicated 4-20 mA Current-Loop Input (165R fixed shunt, no jumper) ---
    block("analog_ma")
    for _ in range(2):
        r_shunt = res("330R", src(source="4-20 mA precision shunt half (330R || 330R = 165.0 ohm; 20 mA = 3.30 V)"))
        r_shunt[1] += ma_term
        r_shunt[2] += gnd

    r_ma_filt = res("10k", src(source="4-20 mA RC low-pass filter & fault current limiter"))
    r_ma_filt[1] += ma_term
    r_ma_filt[2] += ma_mcu

    c_ma_filt = cap("100n 50V", src(source="4-20 mA RC low-pass filter cap (fc = 159 Hz)"))
    c_ma_filt[1] += ma_mcu
    c_ma_filt[2] += gnd

    d_ma = part("Device", "D_Schottky", "SS34", SMA,
                src(mpn="SS34", mfr="MDD", lcsc="C8678",
                    source="4-20 mA overvoltage Schottky clamp to +3V3"),
                ref="D3")
    d_ma["A"] += ma_mcu
    d_ma["K"] += v3

    # --- 2. Dedicated 0-10 V / 0-5 V / 0.4-4.5 V Voltage Input (22k/10k divider) ---
    block("analog_v")
    r_v_top = res("22k", src(source="0-10V / 0-5V divider top (22k/10k -> 10 V = 3.125 V, 4.5 V = 1.406 V)"))
    r_v_top[1] += v0_10_term
    r_v_top[2] += v0_10_mcu

    r_v_bot = res("10k", src(source="0-10V / 0-5V divider bottom (10k to GND)"))
    r_v_bot[1] += v0_10_mcu
    r_v_bot[2] += gnd

    c_v_filt = cap("100n 50V", src(source="0-10V / 0-5V RC low-pass filter cap"))
    c_v_filt[1] += v0_10_mcu
    c_v_filt[2] += gnd

    d_v = part("Device", "D_Schottky", "SS34", SMA,
               src(mpn="SS34", mfr="MDD", lcsc="C8678",
                   source="0-10V input overvoltage Schottky clamp to +3V3"),
               ref="D4")
    d_v["A"] += v0_10_mcu
    d_v["K"] += v3

    # --- 3. Protected Digital / Bus I/O channels (IO1: SDA/RX/PULSE, IO2: SCL/TX) ---
    block("digital_io")
    io_terms = {}
    io_mcus = {}
    for idx in (1, 2):
        t_net = Net(f"IO{idx}_TERM")
        m_net = Net(f"IO{idx}_MCU")
        io_terms[f"io{idx}_term"] = t_net
        io_mcus[f"io{idx}_mcu"] = m_net

        r_pu = res("4k7", src(source=f"IO{idx} 3.3 V pull-up (I2C / UART / Geiger PULSE)"))
        r_pu[1] += v3
        r_pu[2] += m_net

        r_ser = res("330R", src(source=f"IO{idx} series protection resistor"))
        r_ser[1] += t_net
        r_ser[2] += m_net

        d_clamp = part("Device", "D_Schottky", "SS34", SMA,
                       src(mpn="SS34", mfr="MDD", lcsc="C8678",
                           source=f"IO{idx} overvoltage Schottky clamp to +3V3"),
                       ref=f"D{idx + 4}")
        d_clamp["A"] += m_net
        d_clamp["K"] += v3

    # Rail Zener across +5V so clamped fault currents cannot lift the supply rail
    d_rail = part("Device", "D_Zener", "5V6", SOD123,
                  src(mpn="MMSZ5V6T1G", mfr="onsemi", lcsc="C236111",
                      source="Rail overvoltage Zener clamp"),
                  ref="D8")
    d_rail["A"] += gnd
    d_rail["K"] += v5

    # --- 4. SMD 3-Way Changeover Relay (Omron G6S-2F DC5: NC / COM / NO) ---
    block("relay")
    relay_mcu = Net("RELAY_MCU")
    relay_base = Net("RELAY_BASE")
    relay_coil_n = Net("RELAY_COIL_N")
    relay_nc = Net("RELAY_NC")
    relay_com = Net("RELAY_COM")
    relay_no = Net("RELAY_NO")

    r_rel_b = res("1k", src(source="Relay NPN driver base resistor"))
    r_rel_b[1] += relay_mcu
    r_rel_b[2] += relay_base

    r_rel_pd = res("10k", src(source="Relay NPN driver base pull-down (keeps relay off during boot)"))
    r_rel_pd[1] += relay_base
    r_rel_pd[2] += gnd

    q1 = part("Transistor_BJT", "BC847", "MMBT3904", SOT23,
              src(mpn="MMBT3904(RANGE:100-300)", mfr="CJ", lcsc="C20526",
                  source="NPN relay coil driver (40 V, 200 mA, JLCPCB Basic Part; G6S-2F 5V coil draws 28 mA)"),
              ref="Q1")
    q1["B"] += relay_base
    q1["E"] += gnd
    q1["C"] += relay_coil_n

    d_fly = part("Device", "D_Schottky", "SS34", SMA,
                 src(mpn="SS34", mfr="MDD", lcsc="C8678",
                     source="Relay coil flyback suppression diode"),
                 ref="D7")
    d_fly["A"] += relay_coil_n
    d_fly["K"] += v5

    k1 = part("Relay", "G6S-2", "G6S-2F DC5", RELAY_G6S,
              src(mpn="G6S-2F DC5", mfr="Omron", lcsc="C16707",
                  source="Omron G6S-2F DC5 250VAC 2A DPDT SMD changeover relay (both poles parallel: 3/10=NC, 4/9=COM, 5/8=NO)"),
              ref="K1")
    k1[1] += v5
    k1[12] += relay_coil_n
    k1[3] += relay_nc
    k1[10] += relay_nc
    k1[4] += relay_com
    k1[9] += relay_com
    k1[5] += relay_no
    k1[8] += relay_no

    return {
        "ma_term": ma_term,
        "ma_mcu": ma_mcu,
        "v0_10_term": v0_10_term,
        "v0_10_mcu": v0_10_mcu,
        "relay_mcu": relay_mcu,
        "relay_nc": relay_nc,
        "relay_com": relay_com,
        "relay_no": relay_no,
        **io_terms,
        **io_mcus,
    }
