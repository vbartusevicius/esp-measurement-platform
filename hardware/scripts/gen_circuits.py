"""Generate KiCad netlists and schematics for the active variant's boards.

Runs inside the `eda` container:
    python3 hardware/scripts/gen_circuits.py
"""

import builtins
import importlib
import io
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "circuits"))
(Path(__file__).resolve().parents[1] / "build").mkdir(exist_ok=True)
os.chdir(Path(__file__).resolve().parents[1] / "build")

import common
from product_spec import all_boards, load_spec
from skidl import (
    ERC,
    KICAD9,
    generate_netlist,
    reset,
    set_default_tool,
)

BUILD = common.REPO_ROOT / "hardware" / "build"
SPEC = common.SPEC_PATH
DERIVED_BEGIN = "# --- BEGIN GENERATED (hardware/scripts/gen_circuits.py) ---"
DERIVED_END = "# --- END GENERATED ---"


def generate_board(variant, name, build_fn, net_classes):
    reset()
    set_default_tool(KICAD9)
    bdir = BUILD / variant / name
    bdir.mkdir(parents=True, exist_ok=True)
    import skidl as skidl_mod
    skidl_mod.config.backup_lib_file_name = str(BUILD / "gen_circuits_sklib.py")
    import logging
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    skidl_logger = logging.getLogger("skidl")
    skidl_logger.addHandler(handler)
    with redirect_stdout(buf), redirect_stderr(buf):
        build_fn()
        ERC()
        generate_netlist(file_=str(bdir / f"{name}.net"))
    skidl_logger.removeHandler(handler)
    out = buf.getvalue()
    bdir.mkdir(parents=True, exist_ok=True)
    (bdir / "skidl_log.txt").write_text(out)
    parts = [
        {
            "ref": p.ref,
            "value": p.value,
            "footprint": p.footprint,
            "place": p.fields.get("Place", "misc"),
            "lcsc": p.fields.get("LCSC", ""),
            "mpn": p.fields.get("Manufacturer_Part_Number", ""),
            "mfr": p.fields.get("Manufacturer", ""),
            "assembly": p.fields.get("Assembly", "jlc"),
            "source": p.fields.get("Source", ""),
            "footprint_ref": p.fields.get("Footprint_Reference", ""),
            "pins": {str(pin.num): pin.name for pin in p.pins},
        }
        for p in builtins.default_circuit.parts if not p.ref.startswith("#")
    ]
    (bdir / "parts.json").write_text(json.dumps(parts, indent=1))
    return out


def write_derived(net_classes_by_board):
    from blocks import mcu_xiao
    text = SPEC.read_text()
    derived = {
        "mcu_pins": mcu_xiao.MCU_PINS,
        "net_classes": net_classes_by_board,
    }
    block = DERIVED_BEGIN + "\n" + yaml.safe_dump(
        {"derived": derived}, sort_keys=False) + DERIVED_END + "\n"
    if DERIVED_BEGIN in text and DERIVED_END in text:
        pre = text[: text.index(DERIVED_BEGIN)]
        text = pre + block
    else:
        if not text.endswith("\n"):
            text += "\n"
        text += "\n" + block
    SPEC.write_text(text)


def collect_assembly_parts(variant, spec):
    boards = all_boards(spec, variant)
    hand_by_mpn = {}
    all_parts = []
    for b in boards:
        for p in json.loads((BUILD / variant / b / "parts.json").read_text()):
            all_parts.append((b, p))
            if p["assembly"] == "hand":
                entry = hand_by_mpn.setdefault(p["mpn"], {"p": p, "locs": []})
                entry["locs"].append(f"{b} {p['ref']}")

    items = []
    if "102010636" in hand_by_mpn:
        locs = ", ".join(hand_by_mpn["102010636"]["locs"])
        items.append({
            "item": "MCU module (hand-fitted into sockets)",
            "qty": len(hand_by_mpn["102010636"]["locs"]),
            "part": "Seeed Studio XIAO ESP32C6 Pre-Soldered (SKU 102010636)",
            "description": f"ESP32-C6 module with pre-soldered 2x7 pin headers; plugs into the two 5.0 mm female sockets ({locs})",
            "source": "Seeed Studio / Digi-Key / Mouser",
        })
        items.append({
            "item": "XIAO sockets (hand-soldered)",
            "qty": 2 * len(hand_by_mpn["102010636"]["locs"]),
            "part": "1x7 2.54 mm female header, 5.0 mm tall (e.g. Hong Cheng HC-PM254-5.0H)",
            "description": f"1x7 female header, 2.54 mm, 5.0 mm tall, soldered into {locs}; the XIAO stays detachable",
            "source": "LCSC / AliExpress",
        })
    if any(p["mpn"] in ("QG-6428TSWCG02", "FPC-05F-14PH20") for _, p in all_parts):
        items.append({
            "item": "OLED display (14-pin 0.62 mm solder FPC)",
            "qty": 1,
            "part": "QG-6428TSWCG02 / JLX12864OLED-S096W / NFP1312-15AY (0.96 in 64x128 SSD1312 I2C)",
            "description": "0.96 in 64x128 portrait SSD1312 I2C OLED (14.0 x 28.0 x 1.22 mm); 12.0 mm x 9.3 mm flex tail folds through the 9.8 mm top notch on UI and solders directly onto the 14-pad 0.62 mm pitch footprint ui J2",
            "source": "AliExpress (1005003749452625) / Panelook / JLX",
        })
        items.append({
            "item": "OLED backing foam",
            "qty": 2,
            "part": "3.0 mm closed-cell PE double-sided foam tape, 2 strips 1.4 x 26 mm (stacked on the 1.0 mm VHB pre-applied on NFP1312-15AY = 4.0 mm)",
            "description": "on the UI board front under the left/right back edges of the 14.0 x 28.0 mm OLED; "
                           "compresses to 3.8 mm and presses the panel face into the cover's 1.0 mm pocket behind the window",
            "source": "any",
        })

    ffc_links = [lk for lk in spec["boards"].get("interconnects", []) if lk.get("type") == "ffc"]
    if ffc_links:
        pairs = ", ".join(f"{lk['from']} {lk.get('refs', {}).get(lk['from'], 'J6')} <-> {lk['to']} {lk.get('refs', {}).get(lk['to'], 'J1')}" for lk in ffc_links)
        items.append({
            "item": "Main-to-UI FFC cable",
            "qty": len(ffc_links),
            "part": "SHOU HAN FFC-0.5-8P-50mm-B (LCSC C42416274)",
            "description": f"8-pin 0.5 mm reverse/opposite-side (Type B) FFC, 50 mm; {pairs}",
            "source": "LCSC",
        })

    if any(p["ref"] == "JP1" for _, p in all_parts):
        items.append({
            "item": "4-20 mA shunt jumper cap",
            "qty": 1,
            "part": "LCSC C100114",
            "description": "2.54 mm closed jumper cap on main JP1 (closed = 165R 4-20 mA shunt enabled; open = 0-3.3 V voltage input)",
            "source": "LCSC",
        })

    items.append({
        "item": "Case base (snap-fit, no screws)",
        "qty": 1,
        "part": "enclosure/base.stl",
        "description": "PETG or ASA, 0.2 mm layers, rail channel face down; slide the populated main board in "
                       "from the open left side (terminal blocks enter the wall slots), clip THT solder tails to <= 2.5 mm",
        "source": "printed",
    })
    items.append({
        "item": "Case cover (snap-fit, no screws)",
        "qty": 1,
        "part": "enclosure/cover.stl (or cover_embossed.stl)",
        "description": "PETG or ASA, 0.2 mm layers, front face down; the two button bumps stand 0.6 mm proud, so enable "
                       "supports from the build plate (or set BUTTON_TAB boss_height = 0 for a flat face); "
                       "buttons are C-shaped spring tabs in the front wall with plungers (no separate parts); "
                       "slides onto the base from the left",
        "source": "printed",
    })
    return items


def sync_assembly_parts(variant, spec):
    target = common.REPO_ROOT / "hardware/product/assembly_parts.yaml"
    header = ("# Automatically generated by hardware/scripts/gen_circuits.py from parts.json + spec.yaml.\n"
              "# Copied by hardware/scripts/release.py into the release as assembly_parts.csv.\n")
    target.write_text(header + yaml.safe_dump(collect_assembly_parts(variant, spec), sort_keys=False))


def main():
    spec = load_spec()
    variant = spec["active_variant"]
    BUILD.mkdir(parents=True, exist_ok=True)

    pkg = f"variants.{variant}"
    modules = {name: importlib.import_module(f"{pkg}.{name}")
               for name in all_boards(spec, variant)}
    logs = {name: generate_board(variant, name, module.build, module.NET_CLASSES)
            for name, module in modules.items()}
    write_derived({name: module.NET_CLASSES for name, module in modules.items()})
    sync_assembly_parts(variant, spec)

    erc_errors = 0
    netlist_errors = 0
    for name, log in logs.items():
        print(f"=== {name} ===")
        for line in log.splitlines():
            if "ERC" in line or "error" in line.lower():
                print(" ", line)
        erc_errors += sum(1 for line in log.splitlines() if "ERC ERROR" in line)
        netlist_errors += sum(
            1 for line in log.splitlines()
            if line.startswith(("ERROR", "CRITICAL"))
            and "ERC" not in line
            and not ("No footprint for" in line and "/#" in line))
    (BUILD / "skidl_erc.txt").write_text(
        "\n\n".join(f"=== {n} ===\n{l}" for n, l in logs.items()))
    print(f"SKiDL ERC errors: {erc_errors}, non-waived netlist errors: {netlist_errors}")
    return 1 if (erc_errors or netlist_errors) else 0


if __name__ == "__main__":
    sys.exit(main())
