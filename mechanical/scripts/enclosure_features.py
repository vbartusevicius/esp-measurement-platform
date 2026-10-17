"""Enclosure feature positions taken from the real board layouts.

Coordinates: enclosure x centred at 0, y up from the bottom of the hidden
part, z from the rail.
"""

import json
import sys
from itertools import pairwise
from pathlib import Path

import yaml
from ui_stackup import OLED_HEADER_SPACER, OLED_MODULE_BOARD, OLED_PANEL

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "hardware/circuits"))
from product_spec import load_spec

SPEC = load_spec()
VARIANT = SPEC["active_variant"]

DIN = SPEC["din_envelope"]
WALL = SPEC["enclosure"]["wall"]

WIDTH = DIN["modules"] * DIN["module_width"]
HIDDEN_H = DIN["hidden_part"]["height"]
FRONT_H = DIN["front_protrusion"]["height"]
FRONT_D = DIN["front_protrusion"]["depth"]
SHOULDER_H = DIN["shoulder_height"]
TOTAL_D = DIN["hidden_part"]["depth"] + FRONT_D

MAIN_W = SPEC["boards"]["main"]["max_outline"]["width"]
MAIN_H = SPEC["boards"]["main"]["max_outline"]["height"]
UI_W = SPEC["boards"]["ui"]["max_outline"]["width"]
UI_H = SPEC["boards"]["ui"]["max_outline"]["height"]

FRONT_Y_START = (HIDDEN_H - FRONT_H) / 2
FRONT_Y_END = (HIDDEN_H + FRONT_H) / 2

TOP_TERMINAL_REFS = ("J2", "J5")
BOTTOM_TERMINAL_REFS = ("J1", "J4")
ALL_TERMINAL_REFS = TOP_TERMINAL_REFS + BOTTOM_TERMINAL_REFS


def components(board):
    path = REPO / "hardware/build" / VARIANT / board / f"components_{board}.json"
    return {c["ref"]: c for c in json.loads(path.read_text())}


def main_to_enc(x, y):
    return x - MAIN_W / 2, y + (HIDDEN_H - MAIN_H) / 2


def ui_to_enc(x, y):
    return x - UI_W / 2, y + FRONT_Y_START + (FRONT_H - UI_H) / 2


def board_point(board, x, y, n=0.0):
    config = SPEC["boards"][board]
    plane = config.get("plane", "parallel-to-front")
    if plane == "perpendicular-to-rail":
        return config["x"] + n, y + config["y_offset"], config["z_front"] - x
    if plane == "horizontal":
        return y + config["x0"], config["y"] + n, x + config["z0"]
    top = SPEC["front_ui"]["board_top_z"] if board == "ui" else config["z"]
    if board == "main":
        ex, ey = main_to_enc(x, y)
    elif board == "ui":
        ex, ey = ui_to_enc(x, y)
    else:
        x0 = config.get("x0", -config["max_outline"]["width"] / 2)
        ex, ey = x + x0, y + config["y_offset"]
    return ex, ey, top + n


def board_to_enc(board, x, y):
    ex, ey, _ = board_point(board, x, y)
    return ex, ey


def span_box(a, b, **extra):
    return {**extra, "x0": min(a[0], b[0]), "x1": max(a[0], b[0]),
            "y0": min(a[1], b[1]), "y1": max(a[1], b[1]), "z0": min(a[2], b[2]), "z1": max(a[2], b[2])}


def board_slab(board):
    config = SPEC["boards"][board]
    w, h = config["max_outline"]["width"], config["max_outline"]["height"]
    return span_box(board_point(board, 0, 0, -config["thickness"]), board_point(board, w, h, 0.0), board=board)


def board_slabs(board):
    config = SPEC["boards"][board]
    outline = layout_plan(board)["frame"].get("outline")
    if not outline:
        return [board_slab(board)]
    xs = sorted({x for x, _ in outline})
    edges = list(zip(outline, outline[1:] + outline[:1]))
    rects = []
    for x0, x1 in pairwise(xs):
        ys = [ay for (ax, ay), (bx, by) in edges if ay == by and min(ax, bx) <= x0 and max(ax, bx) >= x1]
        rects.append((x0, min(ys), x1, max(ys)))
    t = config["thickness"]
    return [span_box(board_point(board, x0, y0, -t), board_point(board, x1, y1, 0.0), board=board)
            for x0, y0, x1, y1 in rects]


def interconnect_corridor(link):
    ends = [next(p for p in part_boxes() if (p["board"], p["ref"]) == item) for item in link["refs"].items()]
    faces = [b["z1"] if b["z0"] >= board_slab(b["board"])["z1"] - 0.01 else b["z0"] for b in ends]
    return {"x0": min(b["x0"] for b in ends), "x1": max(b["x1"] for b in ends),
            "y0": min(b["y0"] for b in ends), "y1": max(b["y1"] for b in ends),
            "z0": min(faces), "z1": max(faces)}


def horizontal_capacitor():
    return None


def pad_points(comp):
    return [(p[0], p[1]) for p in comp["pads"]]


def bbox_centre(comp):
    b = comp["bbox"]
    return (b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2


def terminal_holes():
    main = components("main")
    return {
        ref: [dict(zip(("x", "y", "z"), board_point("main", *bbox_centre(main[ref]))))]
        for ref in ALL_TERMINAL_REFS if ref in main
    }


def wire_entries():
    """Openings in the top and bottom walls that the KF142R push-in terminals'
    wire-entry faces sit in, flush with the outside."""
    entries = []
    for p in part_boxes():
        if p["board"] == "main" and p["ref"] in ALL_TERMINAL_REFS:
            side = "bottom" if p["ref"] in BOTTOM_TERMINAL_REFS else "top"
            entries.append({"ref": p["ref"], "side": side,
                            "x0": p["x0"], "x1": p["x1"], "z0": p["z0"], "z1": p["z1"]})
    return entries


def layout_plan(board):
    return yaml.safe_load((REPO / "hardware/circuits/variants" / VARIANT / f"layout_{board}.yaml").read_text())


SHOULDER_Z = dict.fromkeys(("bottom", "top"), SPEC["enclosure"]["shoulder_z"])
HIDDEN_D = max(SHOULDER_Z.values())
BASE_TOP_Z = min(SHOULDER_Z.values()) - WALL


def shoulder_of(y):
    return "bottom" if y < HIDDEN_H / 2 else "top"


def connector_faces():
    main = components("main")
    faces = {}
    for ref in TOP_TERMINAL_REFS:
        if ref in main:
            faces[ref] = board_point("main", 0, main[ref]["y"] + 8.40)[1]
    for ref in BOTTOM_TERMINAL_REFS:
        if ref in main:
            faces[ref] = board_point("main", 0, main[ref]["y"] - 8.40)[1]
    return faces


def case_points(board, kind):
    convert = main_to_enc if board == "main" else ui_to_enc
    return [dict(zip(("x", "y"), convert(p["x"], p["y"]))) for p in layout_plan(board).get("case", {}).get(kind, [])]


def legs():
    return case_points("main", "legs")


def pegs():
    return case_points("main", "pegs")


def standoffs():
    return case_points("ui", "standoffs")


def button_holes():
    ui = components("ui")
    return {name: dict(zip(("x", "y"), ui_to_enc(ui[ref]["x"], ui[ref]["y"])))
            for name, ref in (("PROG", "SW1"), ("RESET", "SW2"))}


def led_windows():
    ui = components("ui")
    holes = []
    for ref in ("D1", "D2", "D3"):
        pads = pad_points(ui[ref])
        cx = sum(x for x, _ in pads) / len(pads)
        cy = sum(y for _, y in pads) / len(pads)
        holes.append(dict(zip(("x", "y"), ui_to_enc(cx, cy))))
    return holes


def _oled(key):
    r = layout_plan("ui")["oled_module"][key]
    cx, cy = ui_to_enc(r["x"] + r["w"] / 2, r["y"] + r["h"] / 2)
    return {"cx": cx, "cy": cy, "w": r["w"], "h": r["h"]}


WINDOW_CLEARANCE = 0.2


def oled_window():
    glass = _oled("glass")
    return dict(glass, w=glass["w"] + 2 * WINDOW_CLEARANCE, h=glass["h"] + 2 * WINDOW_CLEARANCE)


def oled_glass():
    return _oled("glass")


def oled_panel():
    mod = layout_plan("ui")["oled_module"]
    return _oled("panel" if "panel" in mod else "glass")


def oled_module():
    return _oled("outline")


def screw_tabs():
    return SPEC["enclosure"].get("screw_tabs", [])


THROUGH_FRONT = {"SW1", "SW2"}
PLUG_REFS = set()


def part_boxes():
    boxes = []
    for board in SPEC["variants"][VARIANT]["boards"]:
        thick = SPEC["boards"][board]["thickness"]
        for ref, c in components(board).items():
            h = c["height"]
            n0, n1 = (-thick - h, -thick) if c["side"] == "back" else (0.0, h)
            b = c["bbox"]
            boxes.append(span_box(board_point(board, b["x0"], b["y0"], n0),
                                  board_point(board, b["x1"], b["y1"], n1),
                                  board=board, ref=ref, through_front=board == "ui" and ref in THROUGH_FRONT))
    top = SPEC["front_ui"]["board_top_z"]
    module_z = top + OLED_HEADER_SPACER
    for ref, key, z0, z1, through in (("OLED board", "outline", module_z, module_z + OLED_MODULE_BOARD, False),
                                      ("OLED glass", "glass", module_z + OLED_MODULE_BOARD,
                                       module_z + OLED_MODULE_BOARD + OLED_PANEL, True)):
        r = _oled(key)
        boxes.append({"board": "ui", "ref": ref, "x0": r["cx"] - r["w"] / 2, "x1": r["cx"] + r["w"] / 2,
                      "y0": r["cy"] - r["h"] / 2, "y1": r["cy"] + r["h"] / 2, "z0": z0, "z1": z1,
                      "through_front": through})
    return boxes
