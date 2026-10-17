"""V1 main board (vertical along the left wall of the 1-DIN case, 39.8 x 78.0 mm,
4 layers, 1.2 mm, two-sided).

Connectors (all JLC-assembled Kefa KF142R-5.08 push-in spring terminals):
  - Bottom shoulder (wire entry facing -y, flush with y=0):
      J1 (KF142R-5.08-2P, 2 poles, SELV domain):
        1 = GND  (DC input ground — on the far side)
        2 = VIN+ (9-30 V DC input, nominal 24 V)
      --- 6.0 mm reinforced isolation keepout + milled PCB slot ---
      J4 (KF142R-5.08-3P, 3 poles, 250 V AC / 2 A RELAY domain):
        1 = NC   (250 V AC / 2 A Relay Normally Closed)
        2 = COM  (250 V AC / 2 A Relay Common)
        3 = NO   (250 V AC / 2 A Relay Normally Open)
  - Top shoulder (wire entry facing +y, flush with y=81):
      J2 (KF142R-5.08-7P, 7 poles, SELV domain):
        1 = GND    (Sensor ground — on the far side)
        2 = +5V    (Regulated 600 mA sensor supply out)
        3 = +24V   (Protected loop supply out)
        4 = 4-20mA (Dedicated 4-20 mA loop input, 165R shunt built-in)
        5 = 0-10V  (Dedicated 0-5V / 0.4-4.5V / 0-10V / 2-10V input, 22k/10k divider)
        6 = IO1    (Protected SDA / RX / Radiation PULSE)
        7 = IO2    (Protected SCL / TX)
  - Internal UI link:
      J3: 8-pin 0.5 mm FFC to the front UI board J1
"""

from builtins import NC

from blocks import mcu_xiao, power_24v, sensor_io
from common import block, part, power, power_flag, src

FPC_8P = "gateway_fp:FPC_Kinghelm_KH-FPC0.5-H1.2SMT-8P"
TERM_2P = "gateway_fp:TerminalBlock_Kefa_KF142R-5.08-2P"
TERM_3P = "gateway_fp:TerminalBlock_Kefa_KF142R-5.08-3P"
TERM_7P = "gateway_fp:TerminalBlock_Kefa_KF142R-5.08-7P"
UI_LINK = ("+3V3", "GND", "BTN_LADDER", "LED_DATA", "+5V", "I2C_SDA", "I2C_SCL", "GND")


def ffc(value, ref, source):
    return part("Connector", "Conn_01x08_Socket", value, FPC_8P,
                src(mpn="KH-FPC0.5-H1.2SMT-8P-QCHF", mfr="Kinghelm", lcsc="C48532769", source=source), ref=ref)


def wire(conn, names, nets):
    for pin, name in enumerate(names, start=1):
        conn[pin] += NC if name is None else nets[name]


def build():
    gnd = power("GND")
    v3 = power("+3V3")
    power_flag(gnd)
    power_flag(v3)

    pwr = power_24v.build(gnd)
    vin_raw, v24_loop, v5 = pwr["vin_raw"], pwr["v24_loop"], pwr["v5"]

    s_io = sensor_io.build(gnd, v3, v5)
    ui = mcu_xiao.build(gnd, v3, v5, s_io)

    block("terminals_bottom")
    j1 = part("Connector", "Screw_Terminal_01x02", "POWER IN (2P push-in)", TERM_2P,
              src(mpn="KF142R-5.08-2P", mfr="Cixi Kefa Elec", lcsc="C475144",
                  source="Bottom-front 2-pole 5.08 mm push-in terminal (SELV): 1=GND, 2=VIN+ (9-30 V)"),
              ref="J1")
    j1[1] += gnd
    j1[2] += vin_raw
    power_flag(vin_raw)

    j4 = part("Connector", "Screw_Terminal_01x03", "RELAY OUT (3P push-in)", TERM_3P,
              src(mpn="KF142R-5.08-3P", mfr="Cixi Kefa Elec", lcsc="C475145",
                  source="Bottom-rear 3-pole 5.08 mm push-in terminal (250 V AC / 2 A isolated): 1=NC, 2=COM, 3=NO"),
              ref="J4")
    j4[1] += s_io["relay_nc"]
    j4[2] += s_io["relay_com"]
    j4[3] += s_io["relay_no"]
    for net in (s_io["relay_nc"], s_io["relay_com"], s_io["relay_no"]):
        power_flag(net)

    block("terminals_top")
    j2 = part("Connector", "Screw_Terminal_01x07", "SENSOR I/O (7P push-in)", TERM_7P,
              src(mpn="KF142R-5.08-7P", mfr="Cixi Kefa Elec", lcsc="C475149",
                  source="Top 7-pole 5.08 mm push-in terminal: 1=GND, 2=+5V, 3=+24V, 4=4-20mA, 5=0-10V (0.4-4.5V/0-10V), 6=IO1 (SDA/RX/PULSE), 7=IO2 (SCL/TX)"),
              ref="J2")
    j2[1] += gnd
    j2[2] += v5
    j2[3] += v24_loop
    j2[4] += s_io["ma_term"]
    j2[5] += s_io["v0_10_term"]
    j2[6] += s_io["io1_term"]
    j2[7] += s_io["io2_term"]

    block("int_ui")
    nets = {
        "BTN_LADDER": ui["btn_ladder"],
        "LED_DATA": ui["led_data"],
        "I2C_SDA": ui["sda"],
        "I2C_SCL": ui["scl"],
        "+5V": v5,
        "+3V3": v3,
        "GND": gnd,
    }
    wire(ffc("UI board", "J3", "8-pin 0.5 mm FFC to the UI board J1"), UI_LINK, nets)


NET_CLASSES = {
    "SELV": [
        "GND", "+3V3", "BTN_LADDER", "LED_DATA", "I2C_SDA", "I2C_SCL",
        "MA_TERM", "MA_MCU", "V0_10_TERM", "V0_10_MCU",
        "IO1_TERM", "IO1_MCU", "IO2_TERM", "IO2_MCU",
        "RELAY_MCU", "RELAY_BASE", "RELAY_COIL_N",
        "BUCK5_SW", "Net-*",
    ],
    "SELV-Power": [
        "VIN_RAW", "VIN_FUSED", "+24V_LOOP", "+5V", "+5V_XIAO",
    ],
    "RELAY-Power": [
        "RELAY_NC", "RELAY_COM", "RELAY_NO",
    ],
}
