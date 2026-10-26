"""V1 main board (vertical along the left wall of the 1-DIN case, 39.8 x 77.4 mm,
4 layers, 1.2 mm).

Connectors (all JLC-assembled push-in spring terminals: Kefa KF142R-5.08 at the bottom,
WAGO 2086 3.5 mm SMD at the top):
  - Bottom shoulder (wire entry facing -y, flush with y=0):
      J1 (KF142R-5.08-2P, 2 poles, SELV domain):
        1 = GND  (DC input ground — on the far side)
        2 = VIN+ (9-30 V DC input, nominal 24 V)
      --- 6.0 mm creepage keepout + milled PCB slot ---
      J4 (KF142R-5.08-3P, 3 poles, RELAY domain, 230 VAC up to 2 A
          resistive via Omron G6B-2114P; 1.5 A inductive):
        1 = COM  (Relay Common)
        2 = NO   (Relay Normally Open)
        3 = NC   (Relay Normally Closed)
  - Top shoulder (wire entry facing +y, flush with y=81): 10-pole sensor bank, SELV domain,
    WAGO 2086-1204 (J2, poles 1-4) + 2086-1203 (J5, poles 5-7) + 2086-1203 (J6, poles 8-10):
        1 = +5V    (Regulated 600 mA sensor supply out)
        2 = +24V   (Protected loop supply out)
        3 = 4-20mA (Dedicated 4-20 mA loop input, 50 mA PTC + 120R shunt built-in)
        4 = 0-10V  (Dedicated 0-5V / 0.4-4.5V / 0-10V / 2-10V input, 22k/10k divider)
        5 = IO1    (Protected ECHO / SDA / RX)
        6 = IO2    (Protected TRIG / SCL / TX)
        7 = IO3    (Protected Geiger PULSE)
        8 = IO4    (Protected meter pulse (dial reader / open collector))
        9 = GND    (Sensor ground)
       10 = GND    (Sensor ground)
  - Internal UI link:
      J3: 8-pin 0.5 mm FFC to the front UI board J1
"""

from builtins import NC

from blocks import mcu_xiao, power_24v, sensor_io
from common import block, part, power, power_flag, src

FPC_8P = "gateway_fp:FPC_Kinghelm_KH-FPC0.5-H1.2SMT-8P"
TERM_2P = "gateway_fp:TerminalBlock_Kefa_KF142R-5.08-2P"
TERM_3P = "gateway_fp:TerminalBlock_Kefa_KF142R-5.08-3P"
WAGO_4P = "gateway_fp:TerminalBlock_WAGO_2086-1204_SMD"
WAGO_3P = "gateway_fp:TerminalBlock_WAGO_2086-1203_SMD"
UI_LINK = ("+3V3", "GND", "BTN_LADDER", "LED_DATA", "+5V", "I2C_SDA", "I2C_SCL", "GND")


def ffc(value, ref, source):
    return part("Connector", "Conn_01x08_Socket", "FPC-05F-8PH20", FPC_8P,
                src(mpn="FPC-05F-8PH20", mfr="XUNPU", lcsc="C2856797", source=source), ref=ref)


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
    j1 = part("Connector", "Screw_Terminal_01x02", "KF142R-5.08-2P", TERM_2P,
              src(mpn="KF142R-5.08-2P", mfr="Cixi Kefa Elec", lcsc="C475144",
                  source="Bottom-front 2-pole 5.08 mm push-in terminal (SELV): 1=GND, 2=VIN+ (9-30 V)"),
              ref="J1")
    j1[1] += gnd
    j1[2] += vin_raw
    power_flag(vin_raw)

    j4 = part("Connector", "Screw_Terminal_01x03", "KF142R-5.08-3P", TERM_3P,
              src(mpn="KF142R-5.08-3P", mfr="Cixi Kefa Elec", lcsc="C475145",
                  source="Bottom-rear 3-pole 5.08 mm push-in terminal (230 VAC relay output): 1=COM, 2=NO, 3=NC"),
              ref="J4")
    j4[1] += s_io["relay_com"]
    j4[2] += s_io["relay_no"]
    j4[3] += s_io["relay_nc"]
    for net in (s_io["relay_nc"], s_io["relay_com"], s_io["relay_no"]):
        power_flag(net)

    block("terminals_top")
    j2 = part("Connector", "Screw_Terminal_01x04", "2086-1204/700-000/997-605", WAGO_4P,
              src(mpn="2086-1204/700-000/997-605", mfr="WAGO", lcsc="C3309718",
                  source="Top sensor bank poles 1..4 (3.5 mm SMD push-in, side entry): 1=+5V, 2=+24V, 3=4-20mA, 4=0-10V"),
              ref="J2")
    j2[1] += v5
    j2[2] += v24_loop
    j2[3] += s_io["ma_term"]
    j2[4] += s_io["v0_10_term"]

    j5 = part("Connector", "Screw_Terminal_01x03", "2086-1203/700-000/997-605", WAGO_3P,
              src(mpn="2086-1203/700-000/997-605", mfr="WAGO", lcsc="C3309626",
                  source="Top sensor bank poles 5..7: 1=IO1 (ECHO/SDA/RX), 2=IO2 (TRIG/SCL/TX), 3=IO3 (Geiger PULSE)"),
              ref="J5")
    j5[1] += s_io["io1_term"]
    j5[2] += s_io["io2_term"]
    j5[3] += s_io["io3_term"]

    j6 = part("Connector", "Screw_Terminal_01x03", "2086-1203/700-000/997-605", WAGO_3P,
              src(mpn="2086-1203/700-000/997-605", mfr="WAGO", lcsc="C3309626",
                  source="Top sensor bank poles 8..10: 1=IO4 (meter pulse), 2=GND, 3=GND"),
              ref="J6")
    j6[1] += s_io["io4_term"]
    j6[2] += gnd
    j6[3] += gnd

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
        "MA_TERM", "MA_SHUNT", "MA_MCU", "V0_10_TERM", "V0_10_MCU",
        "IO1_TERM", "IO1_MCU", "IO2_TERM", "IO2_MCU", "IO3_TERM", "IO3_MCU", "IO4_TERM", "IO4_MCU",
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
