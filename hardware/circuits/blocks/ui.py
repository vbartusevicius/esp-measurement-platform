"""UI block: button ladder (RST/WIFI + PAGE), addressable RGB status LEDs,
14-pin ZIF OLED connector, and the 8-pin FFC interconnect from the main board.
"""

from common import block, part, src
from skidl import Net

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
LED_RGB = "gateway_fp:LED_SK6805-EC15_1.5x1.5mm"
SOT23_5 = "Package_TO_SOT_SMD:SOT-23-5"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
STATUS_LEDS = ("STATUS", "NET", "SENS")
TACT_6X6 = "Button_Switch_SMD:SW_SPST_PTS645Sx43SMTR92"
HDR_4 = "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical"


def res(value, fields=None, footprint=R0603):
    return part("Device", "R", value, footprint, fields)


def cap(value, fields=None, footprint=C0603):
    return part("Device", "C", value, footprint, fields)


def status_leds(gnd, v5, led_data):
    block("leds")
    bulk = cap("1u 50V", src(source="5 V entry from the FFC cable"), footprint=C0805)
    bulk[1] += v5
    bulk[2] += gnd
    buffer = part("74xGxx", "74AHCT1G125", "74AHCT1G125", SOT23_5,
                  src(mpn="SN74AHCT1G125DBVR", mfr="TI", lcsc="C7484",
                      source="TI SN74AHCT1G125 DBV: 1 OE, 2 A, 3 GND, 4 Y, 5 VCC"),
                  ref="U1")
    buffer[1] += gnd
    buffer[2] += led_data
    buffer[3] += gnd
    buffer[5] += v5
    c_buf = cap("100n 50V", src(source="74AHCT1G125 decoupling"))
    c_buf[1] += v5
    c_buf[2] += gnd
    series = res("330R", src(source="SK6805-EC15 datasheet: series resistor at DIN"))
    buffer[4] += series[1]
    data = series[2]
    for i, name in enumerate(STATUS_LEDS):
        led = part("gateway", "SK6805-EC15", "SK6805-EC15", LED_RGB,
                   src(mpn="SK6805-EC15", mfr="OPSCO", lcsc="C2890035",
                       source=f"SK6805-EC15 RGB LED ({name})"),
                   ref=f"D{i + 1}")
        led["DIN"] += data
        led["VDD"] += v5
        led["GND"] += gnd
        c = cap("100n 50V", src(source="SK6805-EC15 datasheet: decoupling per LED"))
        c[1] += v5
        c[2] += gnd
        data = Net(f"LED_CHAIN{i + 1}") if i < len(STATUS_LEDS) - 1 else None
        if data is not None:
            led["DOUT"] += data


BUTTON_B3U = {"footprint": "Button_Switch_SMD:SW_SPST_B3U-1000P", "mpn": "B3U-1000P",
              "mfr": "Omron", "lcsc": "C231329"}


def build_ui_components(gnd, v3, v5, btn_ladder, led_data, sda, scl, oled, button=BUTTON_B3U):
    block("btn_ladder")
    r_pull = res("10k", src(source="Ladder pull-up; no-button = 3V3"))
    r_pull[1] += v3
    r_pull[2] += btn_ladder
    c_ladder = cap("100n 50V", src(source="Ladder debounce/filter cap"))
    c_ladder[1] += btn_ladder
    c_ladder[2] += gnd
    sw1 = part("Switch", "SW_Push", "B3U-1000P", button["footprint"],
               src(mpn=button["mpn"], mfr=button["mfr"], lcsc=button["lcsc"],
                   source="tap: reboot; hold 5 s: WiFi setup / factory reset"))
    r_prog = res("20k", src(source="RST/WIFI ladder: 3V3*20k/30k=2.2V"))
    sw1[1] += btn_ladder
    sw1[2] += r_prog[1]
    r_prog[2] += gnd
    sw2 = part("Switch", "SW_Push", "B3U-1000P", button["footprint"],
               src(mpn=button["mpn"], mfr=button["mfr"], lcsc=button["lcsc"],
                   source="tap: next display page / wake"))
    r_reset = res("10k", src(source="PAGE ladder: 3V3*10k/20k=1.65V; both 1.32V"))
    sw2[1] += btn_ladder
    sw2[2] += r_reset[1]
    r_reset[2] += gnd

    status_leds(gnd, v5, led_data)

    block("oled")
    n_pins = len(oled["pins"])
    if "lcsc" in oled:
        j2 = part("Connector", f"Conn_01x{n_pins:02d}_Socket", "OLED ZIF", oled["footprint"],
                  src(mpn=oled["mpn"], mfr=oled["mfr"], lcsc=oled["lcsc"], source=oled["source"]), ref="J2")
    else:
        j2 = part("Connector", f"Conn_01x{n_pins:02d}_Pin", "OLED", oled.get("footprint", HDR_4),
                  src(mpn=oled["mpn"], mfr=oled.get("mfr", ""), hand=True, source=oled["source"]), ref="J2")
    nets = {"GND": gnd, "VCC": v3, "SCL": scl, "SDA": sda}
    if "RES" in oled["pins"]:
        oled_res = Net("OLED_RES")
        r_res = res("10k", src(source="OLED RES# pull-up"))
        c_res = cap("100n 50V", src(source="OLED RES# RC power-on reset"))
        r_res[1] += v3
        r_res[2] += oled_res
        c_res[1] += oled_res
        c_res[2] += gnd
        nets["RES"] = oled_res
    if "C1P" in oled["pins"]:
        c1p, c1n, c2p, c2n = Net("OLED_C1P"), Net("OLED_C1N"), Net("OLED_C2P"), Net("OLED_C2N")
        iref, vcomh, vout = Net("OLED_IREF"), Net("OLED_VCOMH"), Net("OLED_VOUT")
        c_fly1 = cap("1u 50V", src(source="SSD1312 C1P-C1N charge-pump flying cap"))
        c_fly1[1] += c1p
        c_fly1[2] += c1n
        c_fly2 = cap("1u 50V", src(source="SSD1312 C2P-C2N charge-pump flying cap"))
        c_fly2[1] += c2p
        c_fly2[2] += c2n
        r_iref = res("390k", src(source="SSD1312 IREF segment current reference (390k to GND)"))
        r_iref[1] += iref
        r_iref[2] += gnd
        c_vcomh = cap("1u 50V", src(source="SSD1312 VCOMH deselect decoupling cap"))
        c_vcomh[1] += vcomh
        c_vcomh[2] += gnd
        c_vout = cap("1u 50V", src(source="SSD1312 VCC charge-pump output stabilization cap"))
        c_vout[1] += vout
        c_vout[2] += gnd
        nets.update({"C1P": c1p, "C1N": c1n, "C2P": c2p, "C2N": c2n,
                     "IREF": iref, "VCOMH": vcomh, "VOUT": vout})
    for i, name in enumerate(oled["pins"], start=1):
        if name != "NC":
            j2[i] += nets[name]


NET_CLASSES = {
    "SELV": ["GND", "+3V3", "+5V", "BTN_LADDER", "LED_DATA",
             "LED_CHAIN1", "LED_CHAIN2", "I2C_SDA", "I2C_SCL", "Net-*"],
}
