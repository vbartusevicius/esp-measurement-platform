"""CadQuery wall-mount box for the Universal Sensor Node (non-DIN alternative).

Same boards, no PCB changes. Coordinates are the 1-DIN enclosure's (x across
the DIN width, y up, z from the rail), so the main board, its terminals and
the debossed terminal legend keep their positions:

base   back tray: back wall behind the main board's solder tails, four posts
       on the board's back, side walls with openings for the terminal blocks
       (open towards the lid, so the populated board drops straight in along
       -x), four M3 screw bosses in the side margins and one wall-mount ear on
       each side.
lid    the face parallel to the main board (the DIN enclosure's legend side):
       the debossed terminal legend as on the DIN case and, beside it, the DIN
       cover's UI front rotated 90 deg about y so it faces +x (OLED pocket +
       window, C-shaped spring button tabs, LED baffle windows, standoffs,
       locating blocks and snap arms); filler bars closing the terminal
       openings, a locating lip and four M3 pan-head screw holes.
"""

import sys
from pathlib import Path

import cadquery as cq

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "mechanical/scripts"))
import build_enclosure as be
import enclosure_features as ef
from build_enclosure import box, cylinder

OUT = REPO / "mechanical/build" / f"{ef.VARIANT}-box"

WALL = ef.WALL                  # side walls and lid (the lid matches the DIN front wall: OLED pocket, button tabs)
BACK = 2.0                      # back wall
H = ef.HIDDEN_H                 # 81 mm: terminal faces flush with the top and bottom walls, as in the DIN case
CLEAR = be.FDM_CLEAR
UI_GAP = 1.0                    # UI board back-side parts to the tallest main-board part
MARGIN = 6.0                    # inner margin beyond the main board's right-hand edge (screw bosses)
SIDE = 2.0                      # side walls with the screw bosses (z)

MAIN = ef.board_slab("main")
MAIN_PARTS = [p for p in ef.part_boxes() if p["board"] == "main"]
UI_PARTS_DIN = [p for p in ef.part_boxes() if p["board"] == "ui"]

# Lid outer face: UI stack (back-side parts to the DIN front face) above the tallest main part
XF = round(max(p["x1"] for p in MAIN_PARTS) + UI_GAP + (ef.TOTAL_D - min(p["z0"] for p in UI_PARTS_DIN)) + 0.05, 1)
XI = XF - WALL                  # lid inner face = top of the tray walls
XB = round(MAIN["x0"] - be.THT_TAIL - 0.5 - BACK, 1)   # back outer face

POSTS = [(30.0, 4.5), (30.0, 39.5), (60.0, 4.5), (60.0, 39.5)]   # (y, z) on the main board back, clear of THT pads
POST_D = 4.0
BOSS = {"d": 5.6, "pilot": 2.5, "pilot_depth": 10.0, "hole": 3.4}
BOSS_Y = (6.0, H - 6.0)
EAR = {"thickness": 3.0, "reach": 6.5, "radius": 5.0, "hole": 4.0, "y": H / 2}   # 3.5 mm wood / M3.5 screws
LIP = {"thickness": 1.2, "depth": 2.0, "y": (10.0, H - 10.0)}
SNAP_ARM = {"x_in": 7.3, "beam": 1.0, "width": 6.0, "overlap": 0.5, "hook": 1.8, "ramp": 0.8, "ys": be.SNAP["y"]}
UI_BLOCK = {"gap": 0.15, "len": 3.0, "outer": 8.5, "side_ys": be.UI_RIB["side_ys"], "end_xs": be.UI_RIB["end_xs"],
            "end_w": be.UI_RIB["end_w"], "end_len": 1.5}

# The UI front sits beside the terminal legend (which keeps the DIN layout)
# instead of between its rows: left of the legend in the front view (+z), >= 3
# mm from the leftmost legend text (IO2 / 9-30VDC, z <= 41.6), and raised by DY
# so its FFC connector is closer to main J3 (about 32 mm of folded route).
ZC = 52.0
DY = 6.0
UI_HALF = UI_BLOCK["outer"]     # widest UI front feature (locating blocks) either side of ZC
Z_IN0 = MAIN["z0"] - MARGIN
Z_IN1 = ZC + UI_HALF + 0.6 + LIP["thickness"] + CLEAR   # UI blocks clear of the lid's locating lip
Z0, Z1 = Z_IN0 - SIDE, Z_IN1 + SIDE                     # outer side faces
BOSS_Z = (MAIN["z0"] - 0.5 - BOSS["d"] / 2, Z_IN1 + 0.1 - BOSS["d"] / 2)

def x_cylinder(y, z, x0, x1, diameter):
    """Cylinder along x (posts, bosses, screw holes)."""
    return cq.Workplane("YZ", origin=(x0, 0, 0)).center(y, z).circle(diameter / 2).extrude(x1 - x0)


def to_box(shape):
    """DIN cover frame -> box: the UI front rotated 90 deg about y to face +x."""
    return shape.rotate((0, 0, 0), (0, 1, 0), 90).translate((XF - ef.TOTAL_D, DY, ZC))


def point_to_box(x, y, z):
    return z - ef.TOTAL_D + XF, y + DY, ZC - x


def ui_parts_box():
    """UI component envelopes in box coordinates."""
    parts = []
    for p in UI_PARTS_DIN:
        a, b = point_to_box(p["x0"], p["y0"], p["z0"]), point_to_box(p["x1"], p["y1"], p["z1"])
        parts.append(dict(p, x0=min(a[0], b[0]), x1=max(a[0], b[0]), y0=min(a[1], b[1]), y1=max(a[1], b[1]),
                          z0=min(a[2], b[2]), z1=max(a[2], b[2])))
    return parts


# ---------------------------------------------------------------- UI front (DIN cover frame)

def ui_snap_arms():
    """Freestanding snap arms past the UI board's long edges, hooking behind it."""
    t = SNAP_ARM
    z_free, z_root = be.UI_BOARD_Z - t["hook"], be.FRONT_INNER_Z + 0.01
    arms = []
    for y in t["ys"]:
        for side in (1, -1):
            beam = box(*sorted((side * t["x_in"], side * (t["x_in"] + t["beam"]))), y - t["width"] / 2, y + t["width"] / 2,
                       z_free, z_root)
            hook = box(*sorted((side * (be.UI_W / 2 - t["overlap"]), side * t["x_in"])),
                       y - t["width"] / 2, y + t["width"] / 2, be.UI_BOARD_Z - t["hook"], be.UI_BOARD_Z)
            ramp = "|Y and <Z and " + ("<X" if side > 0 else ">X")
            arms.append(beam.union(hook.edges(ramp).chamfer(t["ramp"])))
    return arms


def ui_blocks():
    """Locating blocks around the UI board edges (gap per side), so buttons and
    LEDs stay within 0.3 mm of their windows."""
    b = UI_BLOCK
    half = be.UI_W / 2
    ui = ef.board_slabs("ui")
    y_lo, y_hi = min(s["y0"] for s in ui), max(s["y1"] for s in ui)
    z0, z1 = be.UI_BOARD_Z - 0.6, be.FRONT_INNER_Z + 0.01
    blocks = []
    for y in b["side_ys"]:
        for s in (-1, 1):
            blocks.append(box(*sorted((s * (half + b["gap"]), s * b["outer"])), y - b["len"] / 2, y + b["len"] / 2, z0, z1))
    for x in b["end_xs"]:
        w = b["end_w"] / 2
        blocks.append(box(x - w, x + w, y_lo - b["gap"] - b["end_len"], y_lo - b["gap"], z0, z1))
        blocks.append(box(x - w, x + w, y_hi + b["gap"], y_hi + b["gap"] + b["end_len"], z0, z1))
    return blocks


def ui_front_features():
    """(bodies, cuts, tab bodies) of the UI front in the DIN cover frame, as on
    the DIN cover: standoffs, LED baffles, snap arms, locating blocks; LED
    windows, OLED window + panel pocket, button C-slots + thinning; then the
    button plungers + bumps, added after the cuts that thin their tabs."""
    bodies = be.standoff_bodies() + be.baffle_bodies() + ui_snap_arms() + ui_blocks()
    cuts = []
    front = (be.FRONT_INNER_Z - 1, ef.TOTAL_D + 1)
    for w in ef.led_windows():
        cuts.append(cylinder(w["x"], w["y"], be.FRONT_INNER_Z - 1, ef.TOTAL_D - be.STACK.led_skin_mm, be.LED_WINDOW))
    win, panel = ef.oled_window(), ef.oled_panel_real()
    cuts.append(box(win["cx"] - win["w"] / 2, win["cx"] + win["w"] / 2, win["cy"] - win["h"] / 2, win["cy"] + win["h"] / 2, *front))
    m = ef.OLED_POCKET_MARGIN
    cuts.append(box(panel["cx"] - panel["w"] / 2 - m, panel["cx"] + panel["w"] / 2 + m,
                    panel["cy"] - panel["h"] / 2 - m, panel["cy"] + panel["h"] / 2 + m,
                    be.FRONT_INNER_Z - 1, be.FRONT_INNER_Z + ef.OLED_POCKET_DEPTH))
    tab_cuts, tab_bodies = be.button_flexures()
    return bodies, cuts + tab_cuts, tab_bodies


# ---------------------------------------------------------------- base

def terminal_openings():
    """Openings in the top/bottom walls for the terminal bodies: CLEAR all
    round, open towards the lid so the populated board drops in along -x."""
    openings = []
    for e in ef.wire_entries():
        y0, y1 = (-1, WALL + 1) if e["side"] == "bottom" else (H - WALL - 1, H + 1)
        openings.append({"ref": e["ref"], "side": e["side"], "x0": e["x0"] - CLEAR, "x1": XI + 1, "top_x": e["x1"],
                         "y0": y0, "y1": y1, "z0": e["z0"] - CLEAR, "z1": e["z1"] + CLEAR})
    return openings


def ear(side):
    """Wall-mount ear on the back plane, sticking out of a side face."""
    e = EAR
    z_wall = Z0 if side < 0 else Z1
    z_hole = z_wall + side * e["reach"]
    plate = box(XB, XB + e["thickness"], e["y"] - e["radius"], e["y"] + e["radius"], *sorted((z_wall - side * 0.01, z_hole)))
    plate = plate.union(x_cylinder(e["y"], z_hole, XB, XB + e["thickness"], 2 * e["radius"]))
    return plate.cut(x_cylinder(e["y"], z_hole, XB - 1, XB + e["thickness"] + 1, e["hole"]))


def build_base():
    base = box(XB, XI, 0, H, Z0, Z1).cut(box(XB + BACK, XI + 1, WALL, H - WALL, Z_IN0, Z_IN1))
    for o in terminal_openings():
        base = base.cut(box(o["x0"], o["x1"], o["y0"], o["y1"], o["z0"], o["z1"]))
    for y, z in POSTS:
        base = base.union(x_cylinder(y, z, XB + BACK - 0.01, MAIN["x0"], POST_D))
    for y in BOSS_Y:
        for z in BOSS_Z:
            base = base.union(x_cylinder(y, z, XB + BACK - 0.01, XI, BOSS["d"]))
            base = base.cut(x_cylinder(y, z, XI - BOSS["pilot_depth"], XI + 1, BOSS["pilot"]))
    for side in (-1, 1):
        base = base.union(ear(side))
    return base


# ---------------------------------------------------------------- lid

def filler_bars():
    """Lid bars closing each terminal opening above the terminal body."""
    bars = []
    for o in terminal_openings():
        wy0, wy1 = (0.0, WALL) if o["side"] == "bottom" else (H - WALL, H)
        bars.append(box(o["top_x"] + CLEAR, XI + 0.01, wy0, wy1, o["z0"] + CLEAR, o["z1"] - CLEAR))
    return bars


def lips():
    l = LIP
    return [box(XI - l["depth"], XI + 0.01, *l["y"], Z_IN0 + CLEAR, Z_IN0 + CLEAR + l["thickness"]),
            box(XI - l["depth"], XI + 0.01, *l["y"], Z_IN1 - CLEAR - l["thickness"], Z_IN1 - CLEAR)]


def terminal_legend():
    """The DIN enclosure's terminal legend, moved from its right wall to the lid face."""
    return be.side_wall_legend_bodies().translate((XF - ef.WIDTH / 2, 0, 0))


def ui_legend():
    """The DIN front's button and LED labels and LED rings, rotated with the UI front."""
    import front_legend as fl
    import legend_color_model as lcm

    bodies = [lcm.inlay(label.path(), ef.TOTAL_D) for label in fl.labels() if fl.face_of(label.y) == "front"]
    bodies += [lcm.led_ring(w) for w in ef.led_windows()]
    combined = bodies[0]
    for body in bodies[1:]:
        combined = combined.union(body)
    return to_box(combined)


def legend():
    """Debossed lid legend: terminal legend + UI labels."""
    return terminal_legend().union(ui_legend())


def build_lid():
    lid = box(XI, XF, 0, H, Z0, Z1)
    for body in filler_bars() + lips():
        lid = lid.union(body)
    bodies, cuts, tab_bodies = ui_front_features()
    for b in bodies:
        lid = lid.union(to_box(b))
    for c in cuts:
        lid = lid.cut(to_box(c))
    for b in tab_bodies:
        lid = lid.union(to_box(b))
    for y in BOSS_Y:
        for z in BOSS_Z:
            lid = lid.cut(x_cylinder(y, z, XI - 1, XF + 1, BOSS["hole"]))
    return lid.cut(legend())


def export_parts(out_dir=OUT):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    parts = {"box_base": build_base(), "box_lid": build_lid()}
    for name, part in parts.items():
        cq.exporters.export(part, str(out_dir / f"{name}.step"), cq.exporters.ExportTypes.STEP)
        cq.exporters.export(part, str(out_dir / f"{name}.stl"), cq.exporters.ExportTypes.STL)
        print(f"{name}: {name}.step + {name}.stl")
    print(f"box: x {XB}..{XF} ({XF - XB:.1f}), y 0..{H}, z {Z0:.1f}..{Z1:.1f} ({Z1 - Z0:.1f}) mm; UI shift y {DY}")
    return parts


if __name__ == "__main__":
    export_parts(sys.argv[1] if len(sys.argv) > 1 else OUT)
