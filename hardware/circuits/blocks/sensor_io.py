"""Universal protected sensor front-end + SMD changeover relay block:
  - 4-20 mA (J2 pin 4 -> XIAO D1 / GPIO1 / ADC1_CH1):
      F2 50 mA / 30 V PTC in series (a stray strand from the adjacent +24V
      pole trips it instead of burning the shunt), then a fixed 120 ohm shunt
      (240R || 240R 1206: 4 mA = 0.48 V, 20 mA = 2.40 V, 24 mA NAMUR fault =
      2.88 V, inside the ESP32-C6 0-3.3 V ADC range), followed by a 10k + 100nF
      RC low-pass (fc = 159 Hz) and a BAT54S clamp to GND and +3V3
      (2 uA max leakage at 25 V -> < 20 mV error through 10k).
  - 0-10V / 0-5V (J2 pin 5 -> XIAO D0 / GPIO0 / ADC1_CH0):
      22k / 10k (10/32 = 0.3125) voltage divider to GND + 100nF filter cap +
      BAT54S clamp to GND and +3V3. Reads 0-10 V (0..3.125 V at ADC), 2-10 V,
      0-5 V and 0.4-4.5 V sensors via Web UI min/max voltage settings.
  - IO1 (J2 pin 6: SDA / RX / Radiation PULSE) & IO2 (J2 pin 7: SCL / TX):
      Each has a 4.7k pull-up to +3V3, 330R series protection resistor, and a
      BAT54S clamp (10 pF max, so I2C rise time stays inside 1 us at 100 kHz).
  - Changeover relay output (J4 pins 1=COM, 2=NO, 3=NC), 230 VAC loads:
      Omron G6B-2114P-US DC5 (SPST-NO + SPST-NC, 5 A 250 VAC resistive,
      1.5 A 250 VAC inductive cos phi 0.4, 3,000 VAC / 6 kV coil-contacts,
      11.0 mm max height). Pins 3 and 6 are joined as COM, so 3-4 is the
      NO contact and 6-5 the NC contact; with J4 ordered COM / NO / NC the
      three contact tracks route without crossing at 2.5 mm spacing.
      NPN Q1 (470R base, forced beta ~11
      at the 60 mA coil current) + SS34 flyback diode.
"""

from common import block, part, src
from skidl import Net

R0603 = "Resistor_SMD:R_0603_1608Metric"
R1206 = "Resistor_SMD:R_1206_3216Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
SMA = "Diode_SMD:D_SMA"
FUSE_1210 = "Fuse:Fuse_1210_3225Metric"
SOD123 = "Diode_SMD:D_SOD-123"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
RELAY_G6B = "gateway_fp:Relay_1A1B_Omron_G6B-2114P"


def res(value, fields=None, footprint=R0603):
    return part("Device", "R", value, footprint, fields)


def cap(value, fields=None, footprint=C0603):
    return part("Device", "C", value, footprint, fields)


def clamp(ref, signal, gnd, v3, what):
    """BAT54S series pair: 1 = A (to GND), 2 = K (to +3V3), 3 = common (signal)."""
    d = part("Diode", "BAT54S", "BAT54S", SOT23,
             src(mpn="BAT54S,215", mfr="Nexperia", lcsc="C47546",
                 source=f"{what} clamp to GND and +3V3 (2 uA max at 25 V, 10 pF max)"),
             ref=ref)
    d[1] += gnd
    d[2] += v3
    d[3] += signal
    return d


def build(gnd, v3, v5):
    ma_term = Net("MA_TERM")
    ma_shunt = Net("MA_SHUNT")
    ma_mcu = Net("MA_MCU")
    v0_10_term = Net("V0_10_TERM")
    v0_10_mcu = Net("V0_10_MCU")

    # --- 1. Dedicated 4-20 mA Current-Loop Input (PTC + 120R fixed shunt, no jumper) ---
    block("analog_ma")
    f_ma = part("Device", "Polyfuse", "50mA", FUSE_1210,
                src(mpn="MF-USMF005-2", mfr="Bourns", lcsc="C118758",
                    source="4-20 mA input PTC: 50 mA hold / 150 mA trip, 30 V"),
                ref="F2")
    f_ma[1] += ma_term
    f_ma[2] += ma_shunt
    for _ in range(2):
        r_shunt = res("240R", src(source="4-20 mA shunt half (240R || 240R = 120 ohm; 20 mA = 2.40 V)"),
                      footprint=R1206)
        r_shunt[1] += ma_shunt
        r_shunt[2] += gnd

    r_ma_filt = res("10k", src(source="4-20 mA RC low-pass filter & clamp current limiter"))
    r_ma_filt[1] += ma_shunt
    r_ma_filt[2] += ma_mcu

    c_ma_filt = cap("100n 50V", src(source="4-20 mA RC low-pass filter cap (fc = 159 Hz)"))
    c_ma_filt[1] += ma_mcu
    c_ma_filt[2] += gnd

    clamp("D3", ma_mcu, gnd, v3, "4-20 mA ADC input")

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

    clamp("D4", v0_10_mcu, gnd, v3, "0-10V ADC input")

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

        clamp(f"D{idx + 4}", m_net, gnd, v3, f"IO{idx}")

    # Rail Zener across +5V so clamped fault currents cannot lift the supply rail
    d_rail = part("Device", "D_Zener", "5V6", SOD123,
                  src(mpn="MMSZ5V6T1G", mfr="onsemi", lcsc="C236111",
                      source="Rail overvoltage Zener clamp"),
                  ref="D8")
    d_rail["A"] += gnd
    d_rail["K"] += v5

    # --- 4. Changeover relay for 230 VAC loads (Omron G6B-2114P-US DC5, 1a + 1b, COM joined on the PCB) ---
    block("relay")
    relay_mcu = Net("RELAY_MCU")
    relay_base = Net("RELAY_BASE")
    relay_coil_n = Net("RELAY_COIL_N")
    relay_nc = Net("RELAY_NC")
    relay_com = Net("RELAY_COM")
    relay_no = Net("RELAY_NO")

    r_rel_b = res("470R", src(source="Relay NPN driver base resistor (5.4 mA for the 60 mA G6B coil)"))
    r_rel_b[1] += relay_mcu
    r_rel_b[2] += relay_base

    r_rel_pd = res("10k", src(source="Relay NPN driver base pull-down (keeps relay off during boot)"))
    r_rel_pd[1] += relay_base
    r_rel_pd[2] += gnd

    q1 = part("Transistor_BJT", "BC847", "MMBT3904", SOT23,
              src(mpn="MMBT3904(RANGE:100-300)", mfr="CJ", lcsc="C20526",
                  source="NPN relay coil driver (40 V, 200 mA, JLCPCB Basic Part; G6B 5 V coil draws 60 mA)"),
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

    k1 = part("gateway", "G6B-2114P", "G6B-2114P-US DC5", RELAY_G6B,
              src(mpn="G6B-2114P-US DC5", mfr="Omron", lcsc="C397217",
                  source="Omron G6B-2114P-US DC5 1a+1b power relay: 5 A 250 VAC, 3 kVAC / 6 kV coil-contacts "
                         "(3+6 = COM, 4 = NO, 5 = NC)"),
              ref="K1")
    k1["8"] += v5
    k1["1"] += relay_coil_n
    k1["3"] += relay_com
    k1["6"] += relay_com
    k1["4"] += relay_no
    k1["5"] += relay_nc

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
