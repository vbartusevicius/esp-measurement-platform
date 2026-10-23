"""Shared helpers for the SKiDL circuit sources.

Every part carries sourcing fields (Manufacturer / Manufacturer_Part_Number /
LCSC / Source / Assembly). Resistors and capacitors take their LCSC part from
PASSIVES, checked against the JLCPCB catalogue; a passive without an entry
stops the build. Parts JLCPCB does not place are marked Assembly=hand.
"""

from pathlib import Path

from product_spec import spec_path
from skidl import KICAD9 as KICAD
from skidl import Net, Part

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = spec_path()
PROJECT_LIB = Path(__file__).resolve().parent / "lib" / "gateway.kicad_sym"


PLACE_BLOCK = "misc"


def block(name):
    """Set the functional block recorded on subsequently created parts."""
    global PLACE_BLOCK
    PLACE_BLOCK = name


PASSIVES = {
    ("R", "1R", "0603"): ("C22936", "UNI-ROYAL", "0603WAF100KT5E"),
    ("R", "330R", "0603"): ("C23138", "UNI-ROYAL", "0603WAF3300T5E"),
    ("R", "470R", "0603"): ("C23179", "UNI-ROYAL", "0603WAF4700T5E"),
    ("R", "680R", "0603"): ("C23228", "UNI-ROYAL", "0603WAF6800T5E"),
    ("R", "750R", "0603"): ("C23241", "UNI-ROYAL", "0603WAF7500T5E"),
    ("R", "1k", "0603"): ("C21190", "UNI-ROYAL", "0603WAF1001T5E"),
    ("R", "4k7", "0603"): ("C23162", "UNI-ROYAL", "0603WAF4701T5E"),
    ("R", "5k1", "0603"): ("C23186", "UNI-ROYAL", "0603WAF5101T5E"),
    ("R", "10k", "0603"): ("C25804", "UNI-ROYAL", "0603WAF1002T5E"),
    ("R", "20k", "0603"): ("C4184", "UNI-ROYAL", "0603WAF2002T5E"),
    ("R", "22k", "0603"): ("C31850", "UNI-ROYAL", "0603WAF2202T5E"),
    ("R", "51k", "0603"): ("C23196", "UNI-ROYAL", "0603WAF5102T5E"),
    ("R", "56k", "0603"): ("C23206", "UNI-ROYAL", "0603WAF5602T5E"),
    ("R", "240R", "1206"): ("C17961", "UNI-ROYAL", "1206W4F2400T5E"),
    ("R", "100k", "0603"): ("C25803", "UNI-ROYAL", "0603WAF1003T5E"),
    ("R", "120k", "0603"): ("C25808", "UNI-ROYAL", "0603WAF1203T5E"),
    ("R", "390k", "0603"): ("C23150", "UNI-ROYAL", "0603WAF3903T5E"),
    ("R", "3R3", "1206"): ("C17945", "UNI-ROYAL", "1206W4F330KT5E"),
    ("R", "27R", "2512"): ("C25478", "UNI-ROYAL", "25121WJ0270T4E"),
    ("C", "18p C0G 50V", "0603"): ("C1647", "Samsung", "CL10C180JB8NNNC"),
    ("C", "47n 50V", "0603"): ("C1622", "Samsung", "CL10B473KB8NNNC"),
    ("C", "100n 50V", "0603"): ("C14663", "YAGEO", "CC0603KRX7R9BB104"),
    ("C", "220n 50V", "0603"): ("C64705", "Samsung", "CL10B224KB8NNNC"),
    ("C", "1u 50V", "0603"): ("C15849", "Samsung", "CL10A105KB8NNNC"),
    ("C", "10u 10V", "0603"): ("C19702", "Samsung", "CL10A106KP8NNNC"),
    ("C", "1u 50V", "0805"): ("C28323", "Samsung", "CL21B105KBFNNNE"),
    ("C", "10u 25V", "0805"): ("C15850", "Samsung", "CL21A106KAYNNNE"),
    ("C", "10u 50V", "0805"): ("C440198", "Murata", "GRM21BR61H106KE43L"),
    ("C", "22u 25V", "0805"): ("C45783", "Samsung", "CL21A226MAQNNNE"),
}


def passive_source(symbol, value, footprint):
    package = footprint.split(":")[1].split("_")[1]
    key = (symbol, value.split(" 1%")[0], package)
    if key not in PASSIVES:
        raise KeyError(f"no verified LCSC part for {key}; add it to PASSIVES")
    lcsc, mfr, mpn = PASSIVES[key]
    return {"Manufacturer": mfr, "Manufacturer_Part_Number": mpn, "LCSC": lcsc}


def part(lib, symbol, value="", footprint="", fields=None, ref=None):
    """Instantiate a stock or project-library part with sourcing fields."""
    lib_ref = str(PROJECT_LIB) if lib == "gateway" else lib
    p = Part(lib_ref, symbol, tool=KICAD, tag=PLACE_BLOCK, **({"ref": ref} if ref else {}))
    if value:
        p.value = value
    if footprint:
        p.footprint = footprint
    p.fields["Place"] = PLACE_BLOCK
    p.fields["Assembly"] = "jlc"
    for key, val in (fields or {}).items():
        p.fields[key] = val
    if lib == "Device" and symbol in ("R", "C"):
        for key, val in passive_source(symbol, value, footprint).items():
            p.fields[key] = val
    return p


def src(mpn="", mfr="", lcsc="", source="", hand=False, footprint_ref=""):
    fields = {"Manufacturer": mfr, "Manufacturer_Part_Number": mpn, "LCSC": lcsc,
              "Source": source, "Footprint_Reference": footprint_ref}
    if hand:
        fields["Assembly"] = "hand"
    return fields


def power(name):
    net = Net(name)
    sym = Part("power", name, tool=KICAD, tag="power")
    sym.footprint = ""
    sym["1"] += net
    return net


def power_flag(net):
    flag = Part("power", "PWR_FLAG", tool=KICAD, tag="power")
    flag.footprint = ""
    flag["1"] += net
