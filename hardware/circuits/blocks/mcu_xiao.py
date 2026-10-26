"""MCU block: Seeed XIAO ESP32C6 on 2x7 female 2.54mm headers, powered
from the 24V->5V buck via a TI LM66100 ideal diode so USB-C service power
cannot back-feed the 5V sensor rail or 24V buck.

Unified XIAO ESP32-C6 Pin Map:
  1  (D0 / GPIO0)  = V0_10_MCU   -> Dedicated 0-10V / 0-5V / 0.4-4.5V analog input (ADC1_CH0, J2.5)
  2  (D1 / GPIO1)  = MA_MCU      -> Dedicated 4-20 mA loop analog input (ADC1_CH1, 120R shunt, J2.4)
  3  (D2 / GPIO2)  = BTN_LADDER  -> UI board 2-button ADC resistor ladder (ADC1_CH2)
  4  (D3 / GPIO21) = LED_DATA    -> UI board 3x SK6805-EC15 RGB LEDs via 5 V buffer
  5  (D4 / GPIO22) = I2C_SDA     -> UI board SSD1312 OLED SDA (4.7k pull-up to +3V3)
  6  (D5 / GPIO23) = I2C_SCL     -> UI board SSD1312 OLED SCL (4.7k pull-up to +3V3)
  7  (D6 / GPIO16) = IO2_MCU     -> Protected sensor IO2: TRIG / SCL / TX (J2 pole 6)
  8  (D7 / GPIO17) = IO1_MCU     -> Protected sensor IO1: ECHO / SDA / RX (J2 pole 5)
  9  (D8 / GPIO19) = RELAY_MCU   -> 230 VAC changeover relay driver (J4.1 COM, J4.2 NO, J4.3 NC)
  10 (D9 / GPIO20) = IO3_MCU     -> Protected sensor IO3: Geiger PULSE (J2 pole 7)
  11 (D10/ GPIO18) = IO4_MCU     -> Protected sensor IO4: meter pulse (J2 pole 8)
  12 (3V3)         = +3V3        -> 3.3 V output from XIAO regulator for logic & OLED
  13 (GND)         = GND         -> System ground
  14 (5V)          = +5V_XIAO    -> Fed from +5V buck through LM66100 ideal diode
"""

from builtins import NC

from common import block, part, src
from skidl import Net

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
SC70_6 = "Package_TO_SOT_SMD:SOT-363_SC-70-6"
XIAO_FP = "gateway_fp:XIAO_ESP32C6_Header"

MCU_PINS = {
    "v0_10_sense": {"pin": "D0/GPIO0", "net": "V0_10_MCU", "note": "ADC1_CH0: 0-10V / 0-5V / 0.4-4.5V / 2-10V input (22k/10k divider, J2 pole 4)"},
    "ma_sense": {"pin": "D1/GPIO1", "net": "MA_MCU", "note": "ADC1_CH1: 4-20 mA current-loop input (50 mA PTC + 120R shunt: 20 mA = 2.40 V, J2 pole 3)"},
    "button_ladder": {"pin": "D2/GPIO2", "net": "BTN_LADDER", "note": "ADC1_CH2: RST/WIFI + PAGE buttons on UI board"},
    "led_data": {"pin": "D3/GPIO21", "net": "LED_DATA", "note": "SK6805 RGB LED chain via 5 V buffer on UI"},
    "i2c_sda": {"pin": "D4/GPIO22", "net": "I2C_SDA", "note": "Internal I2C SDA to OLED on UI board"},
    "i2c_scl": {"pin": "D5/GPIO23", "net": "I2C_SCL", "note": "Internal I2C SCL to OLED on UI board"},
    "io2_bus_tx_scl": {"pin": "D6/GPIO16", "net": "IO2_MCU", "note": "Protected sensor IO2: ultrasonic TRIG / I2C SCL / UART TX (J2 pole 6)"},
    "io1_bus_rx_sda": {"pin": "D7/GPIO17", "net": "IO1_MCU", "note": "Protected sensor IO1: ultrasonic ECHO / I2C SDA / UART RX (J2 pole 5)"},
    "relay_ctrl": {"pin": "D8/GPIO19", "net": "RELAY_MCU", "note": "Drives Omron G6B-2114P-US DC5 changeover relay (J4.1 COM, J4.2 NO, J4.3 NC; 230 VAC 2 A)"},
    "io3_pulse": {"pin": "D9/GPIO20", "net": "IO3_MCU", "note": "Protected sensor IO3: Geiger counter PULSE (J2 pole 7)"},
    "io4_pulse": {"pin": "D10/GPIO18", "net": "IO4_MCU", "note": "Protected sensor IO4: meter pulse (dial reader / open collector) (J2 pole 8)"},
}


def res(value, fields=None, footprint=R0603, ref=None):
    return part("Device", "R", value, footprint, fields, ref=ref)


def cap(value, fields=None, footprint=C0603):
    return part("Device", "C", value, footprint, fields)


def build(gnd, v3, v5_buck, s_io):
    v5_xiao = Net("+5V_XIAO")
    btn_ladder = Net("BTN_LADDER")
    sda = Net("I2C_SDA")
    scl = Net("I2C_SCL")
    led_data = Net("LED_DATA")

    block("mcu_power")
    d_ideal = part("Power_Management", "LM66100DCK", "LM66100", SC70_6,
                   src(mpn="LM66100DCKR", mfr="TI", lcsc="C2869734",
                       source="TI LM66100 ideal diode: prevents USB-C back-feeding +5V sensor rail & buck"),
                   ref="U2")
    d_ideal["VIN"] += v5_buck
    d_ideal["~{CE}"] += gnd
    d_ideal["GND"] += gnd
    d_ideal["VOUT"] += v5_xiao
    d_ideal["ST"] += NC

    c_v5 = cap("10u 10V", src(source="XIAO 5V input decoupling"))
    c_v5[1] += v5_xiao
    c_v5[2] += gnd

    block("mcu")
    u3 = part("gateway", "XIAO_ESP32C6", "XIAO ESP32C6", XIAO_FP,
              src(mpn="102010636", mfr="Seeed Studio", hand=True, footprint_ref="C9900124963",
                  source="XIAO ESP32C6 Pre-Soldered on two 1x7 5.0 mm female socket strips"),
              ref="U3")
    u3["1"] += s_io["v0_10_mcu"]  # D0/GPIO0 (ADC1_CH0)
    u3["2"] += s_io["ma_mcu"]     # D1/GPIO1 (ADC1_CH1)
    u3["3"] += btn_ladder         # D2/GPIO2 (ADC1_CH2)
    u3["4"] += led_data           # D3/GPIO21
    u3["5"] += sda                # D4/GPIO22
    u3["6"] += scl                # D5/GPIO23
    u3["7"] += s_io["io2_mcu"]    # D6/GPIO16
    u3["8"] += s_io["io1_mcu"]    # D7/GPIO17
    u3["9"] += s_io["relay_mcu"]  # D8/GPIO19
    u3["10"] += s_io["io3_mcu"]   # D9/GPIO20
    u3["11"] += s_io["io4_mcu"]   # D10/GPIO18
    u3["12"] += v3                # 3V3 regulator output
    u3["13"] += gnd               # GND
    u3["14"] += v5_xiao           # 5V input

    c_v3 = cap("10u 10V", src(source="+3V3 rail decoupling"))
    c_v3[1] += v3
    c_v3[2] += gnd

    for net_, ref in ((sda, "R16"), (scl, "R17")):   # refs fixed: IO3/IO4 parts use R18..R21
        r = res("4k7", src(source="Internal OLED I2C pull-up"), ref=ref)
        r[1] += v3
        r[2] += net_

    return {
        "v3": v3,
        "btn_ladder": btn_ladder,
        "led_data": led_data,
        "sda": sda,
        "scl": scl,
    }
