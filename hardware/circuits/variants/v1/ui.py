"""V1 UI board (1 DIN front, 13.8 x 40.5 mm): 0.96" 64x128 SSD1312 portrait
OLED (QG-6428TSWCG02 / JLX12864OLED-S096W / NFP1312-15AY, 14.0 x 28.0 x 1.22 mm)
connected via a 14-pin 0.62 mm pitch direct-solder FPC footprint J2 on the back
with its 3.3 V charge-pump passives on the back, two Omron B3U-1000P switches
pressed through printed plungers, and three SK6805 RGB LEDs below the buttons;
FFC J1 to the main board."""

from blocks import ui
from common import block, power, power_flag
from skidl import Net

from variants.v1.main import UI_LINK, ffc, wire

SSD1312_64X128_HOTBAR14 = {
    "footprint": "gateway_fp:OLED_FPC_14P_P0.62mm_Hotbar",
    "mpn": "QG-6428TSWCG02",
    "mfr": "Allvision / JLX",
    "pins": ("C2P", "C2N", "C1P", "C1N", "VCC", "NC", "GND", "VCC", "RES", "SCL", "SDA", "IREF", "VCOMH", "VOUT"),
    "source": "14-pin 0.62 mm pitch (P0.62x13=8.06 mm, 12.0 mm tail, 9.3 mm wide) soldering FPC footprint on the back "
              "of the UI board receiving the folded flex tail of the 0.96in 64x128 SSD1312 portrait I2C OLED "
              "(QG-6428TSWCG02 / JLX12864OLED-S096W / NFP1312-15AY, 14.0x28.0x1.22 mm)",
}


def build():
    gnd = power("GND")
    power_flag(gnd)
    names = ("+3V3", "BTN_LADDER", "I2C_SDA", "I2C_SCL", "+5V", "LED_DATA")
    v3, btn_ladder, sda, scl, v5, led_data = (Net(n) for n in names)
    for net in (v3, v5):
        power_flag(net)
    block("int_main")
    wire(ffc("Main board", "J1", "8-pin 0.5 mm FFC to main J3"), UI_LINK,
         {"+3V3": v3, "GND": gnd, "BTN_LADDER": btn_ladder, "LED_DATA": led_data,
          "+5V": v5, "I2C_SDA": sda, "I2C_SCL": scl})
    ui.build_ui_components(gnd, v3, v5, btn_ladder, led_data, sda, scl, oled=SSD1312_64X128_HOTBAR14)


NET_CLASSES = dict(ui.NET_CLASSES)
