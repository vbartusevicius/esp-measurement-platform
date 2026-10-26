"""CadQuery 1-DIN (18 mm) side-opening enclosure for the Universal Sensor Node.

base   rail side, z -5..shoulder: a TS35 channel in the 5 mm deep back
       (EN 60715: 35 +-0.3 between lips, 1 mm lips) with a fixed hook under
       the top lip and a sprung sliding latch under the bottom lip. Open on
       the left side (-x) so the populated main board slides straight in (+x).
       Top wall has slots for J2 + J5 + J6 (10-pole sensor bank), bottom wall for
       J1 (power) and J4 (relay); every slot runs out of the open left side so
       the terminal bodies, which overhang the board edge into the walls, can
       slide in, and has FDM_CLEAR all round the terminal body.
cover  front side + left side wall, slides on from the left (+x): filler bars
       that close the terminal slots, recesses over the main board's THT
       solder tails, shoulder plates, front protrusion (0.96" 64x128 OLED
       panel pocket behind the active-area window, C-shaped spring button tabs
       with a front bump and a plunger, LED baffle windows), UI board snap hooks, side
       locating ribs and standoffs, and four side snap-click hooks into the base.
"""

import math
import sys
from pathlib import Path

import cadquery as cq

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "mechanical/scripts"))
from enclosure_features import (
    BASE_TOP_Z,
    FRONT_Y_END,
    FRONT_Y_START,
    HIDDEN_H,
    OLED_POCKET_DEPTH,
    OLED_POCKET_MARGIN,
    board_slabs,
    oled_panel_real,
    part_boxes,
    SHOULDER_Z,
    SPEC,
    TOTAL_D,
    VARIANT,
    WIDTH,
    board_point,
    board_slab,
    button_holes,
    components,
    horizontal_capacitor,
    led_windows,
    legs,
    oled_window,
    pegs,
    screw_tabs,
    shoulder_of,
    standoffs,
    wire_entries,
)
from ui_stackup import compute_ui_stackup

WALL = SPEC["enclosure"]["wall"]
MAIN_Z = SPEC["boards"]["main"].get("z", 21.2)
MAIN_THICK = SPEC["boards"]["main"]["thickness"]
MAIN_BOTTOM_Z = MAIN_Z - MAIN_THICK
STACK = compute_ui_stackup()
UI_BOARD_Z = STACK.board_z
UI_BOARD_TOP_Z = STACK.board_top_z
UI_W = SPEC["boards"]["ui"]["max_outline"]["width"]

INNER_W = WIDTH - 2 * WALL
INNER_H = HIDDEN_H - 2 * WALL
FRONT_INNER_Z = TOTAL_D - WALL

LEG_SIZE = 5.0
PEG_DIAMETER = 3.0
STANDOFF_DIAMETER = 2.4
LED_WINDOW = 2.2
BAFFLE_WALL = 0.4
BUTTON_HOLE = 2.6  # legend ring diameter drawn around each button tongue
FDM_CLEAR = 0.2    # per side, between printed parts and around PCB/terminal bodies
# C-shaped spring tab per button (same geometry as knx-dali-gateway v3): a
# round pad over the switch on an arm rooted at a shared centre bridge, both
# thinned to `thickness`; rounded bump on the front, plunger behind the pad.
BUTTON_TAB = {"pad": 2.6, "arm": 2.0, "root_x": 0.9, "slot": 0.45, "thickness": 0.7, "nub": 1.4,
              "nub_gap": 0.1, "boss": 2.0, "boss_height": 0.6, "boss_round": 0.25}
THT_TAIL = 2.5     # max solder-tail protrusion behind the main board (clip longer leads)
THT_RECESS = 1.0   # recess depth in the cover's left wall over THT tails
UI_RIB = {"gap": 0.15, "len": 3.0, "side_ys": (23.0, 40.5, 58.0), "end_xs": (-6.0, 6.0), "end_w": 1.5}
SCREW_HOLE = 3.2
CASE_SCREW = {"pilot": 2.2, "clearance": 2.8, "depth": 8.5, "z": BASE_TOP_Z - 2.0}
SCREW_TAB = {"width": 4.0, "depth": 8.5, "z0": 39.85}
LIP = {"thickness": 1.2, "depth": 2.0}
SNAP = {"overlap": 0.5, "width": 6.0, "slot": 0.5, "hook_height": 1.8, "free_end_below_board": 1.8,
        "y": (FRONT_Y_START + 12, FRONT_Y_END - 12)}

RAIL = {"centre": HIDDEN_H / 2, "slot": 35.4, "lip": 1.0, "clearance": 0.1}
BACK_DEPTH = 5.0
HOOK_REACH = 1.5
LATCH = {"half_width": min(5.0, WIDTH / 2 - 4.5), "gap": 0.4, "tab_bottom": -6.0, "beam": 0.8,
         "beam_ys": (9.0, 11.4), "beam_reach": min(16.0, WIDTH / 2 - 1.5), "hole": (4.0, 2.0),
         "hole_y": -4.0, "travel": 2.0}


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def cylinder(x, y, z0, z1, diameter):
    return cq.Workplane("XY").circle(diameter / 2).extrude(z1 - z0).translate((x, y, z0))


def capacitor_cradles():
    return []


def rail_edges():
    return RAIL["centre"] - RAIL["slot"] / 2, RAIL["centre"] + RAIL["slot"] / 2


def lip_z():
    top = -(RAIL["lip"] + RAIL["clearance"])
    return top - 1.5, top


def rail_blocks():
    low, high = rail_edges()
    back = -BACK_DEPTH
    blocks = box(-WIDTH / 2, WIDTH / 2, 0, low, back, 0).union(box(-WIDTH / 2, WIDTH / 2, high, HIDDEN_H, back, 0))
    reach = min(15.0, WIDTH / 2 - 1.0)
    hook = box(-reach, reach, high - HOOK_REACH, high, *lip_z())
    return blocks.union(hook)


def latch_parts():
    low, _ = rail_edges()
    back = -BACK_DEPTH
    w, g, b = LATCH["half_width"], LATCH["gap"], LATCH["beam"]
    reach = LATCH["beam_reach"]
    y0, y1 = LATCH["beam_ys"]
    y2 = y1 + (y1 - y0)
    pocket = box(-w - g, w + g, LATCH["tab_bottom"] - 1, low + 1, back - 1, 0).union(
        box(-reach - g, reach + g, y0 - LATCH["travel"], y2 + b + g, back - 1, 0))
    bar_z = (back, -g)
    bar = box(-w, w, LATCH["tab_bottom"], low - g, *bar_z)
    lip = box(-w, w, low - g, low + HOOK_REACH, *lip_z())
    lip = lip.edges("|X and <Z and >Y").chamfer(1.0)
    latch = bar.union(lip)
    for s in (-1, 1):
        leg1 = box(*sorted((s * w, s * (reach - g))), y0, y0 + b, *bar_z)
        turn1 = box(*sorted((s * (reach - g - b), s * (reach - g))), y0, y1 + b, *bar_z)
        leg2 = box(*sorted((s * (w + g), s * (reach - g))), y1, y1 + b, *bar_z)
        turn2 = box(*sorted((s * (w + g), s * (w + g + b))), y1, y2 + b, *bar_z)
        leg3 = box(*sorted((s * (w + g), s * (reach + g + 0.5))), y2, y2 + b, *bar_z)
        for seg in (leg1, turn1, leg2, turn2, leg3):
            latch = latch.union(seg)
    hole_w, hole_h = LATCH["hole"]
    hole = box(-hole_w / 2, hole_w / 2, LATCH["hole_y"] - hole_h / 2, LATCH["hole_y"] + hole_h / 2, back - 1, 1)
    return pocket, latch.cut(hole)


def leg_bodies():
    h = LEG_SIZE / 2
    return [box(p["x"] - h, p["x"] + h, p["y"] - h, p["y"] + h, WALL, MAIN_BOTTOM_Z) for p in legs()]


SIDE_SNAP_YS = (16.0, 63.8)  # right-side snap hooks, >= 0.5 mm clear of the J1/J4 and J2/J5/J6 bodies


def shoulder_snap_bodies():
    """Four side snap-click hooks on the cover locking into the base."""
    if screw_tabs():
        return []
    bodies = []
    for y_c in SIDE_SNAP_YS:
        tongue = box(INNER_W / 2 - 1.1, INNER_W / 2, y_c - 1.2, y_c + 1.2, 39.2, BASE_TOP_Z + 0.4)
        barb = box(INNER_W / 2 - 1.1, INNER_W / 2 + 0.5, y_c - 1.2, y_c + 1.2, 39.2, 40.4)
        bodies.append(tongue.union(barb))
    for y_wall, d in ((WALL, 1), (HIDDEN_H - WALL, -1)):
        y0, y1 = sorted((y_wall, y_wall + d * 1.1))
        yb0, yb1 = sorted((y_wall - d * 0.5, y_wall + d * 1.1))
        tongue = box(-WIDTH / 2, -INNER_W / 2 + 1.2, y0, y1, 9.0, 14.0)
        barb = box(-INNER_W / 2, -INNER_W / 2 + 1.2, yb0, yb1, 9.0, 14.0)
        bodies.append(tongue.union(barb))
    return bodies


def shoulder_snap_keepers():
    if screw_tabs():
        return []
    keepers = [box(INNER_W / 2 - 0.1, INNER_W / 2 + 0.6, y_c - 1.4, y_c + 1.4, 39.0, 40.6)
               for y_c in SIDE_SNAP_YS]
    keepers += [box(-INNER_W / 2 - 0.1, -INNER_W / 2 + 1.3, WALL - 0.6, WALL + 0.1, 8.8, 14.2),
                box(-INNER_W / 2 - 0.1, -INNER_W / 2 + 1.3, HIDDEN_H - WALL - 0.1, HIDDEN_H - WALL + 0.6, 8.8, 14.2)]
    return keepers


def screw_tab_bodies():
    return list(shoulder_snap_bodies())


def terminal_slots():
    """Wall slots for the terminal blocks: FDM_CLEAR around the body and open
    to the left side so the populated board slides in along +x."""
    slots = []
    for s in wire_entries():
        y0, y1 = (-1, WALL + 1) if s.get("side") == "bottom" else (HIDDEN_H - WALL - 1, HIDDEN_H + 1)
        slots.append({"ref": s["ref"], "side": s.get("side"), "x0": -WIDTH / 2 - 1, "x1": s["x1"] + FDM_CLEAR,
                      "y0": y0, "y1": y1, "z0": s["z0"] - FDM_CLEAR, "z1": s["z1"] + FDM_CLEAR,
                      "body_x0": s["x0"]})
    return slots


def slot_filler_bodies():
    """Cover bars that close each terminal slot left of the terminal body,
    tied into the cover's left wall."""
    bodies = []
    for s in terminal_slots():
        wy0, wy1 = (0.0, WALL) if s["side"] == "bottom" else (HIDDEN_H - WALL, HIDDEN_H)
        ty0, ty1 = (WALL - 0.01, WALL + FDM_CLEAR + 0.5) if s["side"] == "bottom" else \
            (HIDDEN_H - WALL - FDM_CLEAR - 0.5, HIDDEN_H - WALL + 0.01)
        z0, z1 = s["z0"] + FDM_CLEAR, s["z1"] - FDM_CLEAR
        bodies.append(box(-WIDTH / 2, s["body_x0"] - FDM_CLEAR, wy0, wy1, z0, z1)
                      .union(box(-WIDTH / 2, -INNER_W / 2, ty0, ty1, z0, z1)))
    return bodies


def tht_tail_recesses():
    """Pockets in the cover's left wall over the main board's through-hole
    solder tails (terminal blocks, XIAO sockets)."""
    back = SPEC["boards"]["main"]["x"] - MAIN_THICK
    depth_x = back - THT_TAIL - 0.3
    pockets = []
    for comp in components("main").values():
        pts = [board_point("main", x, y) for x, y in comp.get("tht_pads", [])]
        if not pts:
            continue
        ys, zs = [p[1] for p in pts], [p[2] for p in pts]
        pockets.append(box(min(depth_x, -INNER_W / 2 - THT_RECESS), -INNER_W / 2 + 0.01,
                           max(WALL + FDM_CLEAR, min(ys) - 1.4), min(HIDDEN_H - WALL - FDM_CLEAR, max(ys) + 1.4),
                           max(WALL + FDM_CLEAR, min(zs) - 1.4), min(BASE_TOP_Z, max(zs) + 1.4)))
    return pockets


def walls_clip(solid):
    return solid.intersect(box(-WIDTH / 2, WIDTH / 2, 0, HIDDEN_H, -BACK_DEPTH, BASE_TOP_Z))


SIDE_DEBOSS = 0.35


def _pin_z_positions(ref):
    """Map pin_number -> enclosure z coordinate for a terminal block on main."""
    comp = components("main")[ref]
    by_pin = {}
    for px, py, num in comp["pads"]:
        _, _, ez = board_point("main", px, py)
        by_pin.setdefault(str(num), []).append(ez)
    return {k: sum(v) / len(v) for k, v in by_pin.items()}


def _side_text_solid(text, z_anchor, y_centre, height, align="center"):
    """Build a 3D text solid on the right side wall (x = WIDTH/2 - SIDE_DEBOSS .. WIDTH/2)
    readable left-to-right when viewing the right side wall from +x (where +z is left
    and -z is right). `align='left'` aligns the left edge of the text to `z_anchor`."""
    from matplotlib.path import Path as MplPath
    from matplotlib.textpath import TextPath
    from matplotlib.transforms import Affine2D

    raw = TextPath((0, 0), text, size=height, prop={"family": "DejaVu Sans", "weight": "bold"})
    ext = raw.get_extents()
    if align == "left":
        tx = z_anchor + ext.x0
    elif align == "right":
        tx = z_anchor + ext.x0 + ext.width
    else:
        tx = z_anchor + ext.x0 + ext.width / 2
    placed = raw.transformed(Affine2D().scale(-1.0, 1.0).translate(
        tx,
        y_centre - ext.y0 - ext.height / 2,
    ))
    polygons = [p for p in placed.to_polygons(closed_only=True) if len(p) > 3]
    nested = []
    for i, ring in enumerate(polygons):
        depth = sum(MplPath(other).contains_point(ring[0]) for j, other in enumerate(polygons) if j != i)
        nested.append((depth, [(float(pt[1]), float(pt[0])) for pt in ring[:-1]]))
    nested.sort(key=lambda item: item[0])

    x0 = WIDTH / 2 - SIDE_DEBOSS
    solid = None
    for depth, pts_yz in nested:
        body = cq.Workplane("YZ", origin=(x0, 0, 0)).polyline(pts_yz).close().extrude(SIDE_DEBOSS)
        if depth % 2 == 0:
            solid = body if solid is None else solid.union(body)
        elif solid is not None:
            solid = solid.cut(body)
    return solid


def _side_line(z0, y0, z1, y1, lw=0.45):
    """Debossed line segment on the right side wall (x = WIDTH/2 - SIDE_DEBOSS .. WIDTH/2)."""
    import math
    x0 = WIDTH / 2 - SIDE_DEBOSS
    dx, dy = z1 - z0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-4:
        return None
    nx, ny = -dy / length * (lw / 2), dx / length * (lw / 2)
    pts_yz = [
        (y0 + ny, z0 + nx),
        (y1 + ny, z1 + nx),
        (y1 - ny, z1 - nx),
        (y0 - ny, z0 - nx),
    ]
    return cq.Workplane("YZ", origin=(x0, 0, 0)).polyline(pts_yz).close().extrude(SIDE_DEBOSS)


def _side_dot(z_c, y_c, radius=0.65):
    x0 = WIDTH / 2 - SIDE_DEBOSS
    return cq.Workplane("YZ", origin=(x0, 0, 0)).center(y_c, z_c).circle(radius).extrude(SIDE_DEBOSS)


def _side_text_vertical(text, z_centre, y_top, height):
    """Text on the right side wall reading bottom to top (rotated 90 deg
    counter-clockwise as seen from +x), centred on z_centre, ending at y_top."""
    from matplotlib.path import Path as MplPath
    from matplotlib.textpath import TextPath

    raw = TextPath((0, 0), text, size=height, prop={"family": "DejaVu Sans", "weight": "bold"})
    ext = raw.get_extents()
    b_mid = (ext.y0 + ext.y1) / 2
    polygons = [p for p in raw.to_polygons(closed_only=True) if len(p) > 3]
    nested = []
    for i, ring in enumerate(polygons):
        depth = sum(MplPath(other).contains_point(ring[0]) for j, other in enumerate(polygons) if j != i)
        # text (a along the baseline, b up) -> wall (y = up, z = left as seen from +x)
        nested.append((depth, [(float(y_top - ext.x1 + a), float(z_centre + b - b_mid)) for a, b in ring[:-1]]))
    nested.sort(key=lambda item: item[0])
    x0 = WIDTH / 2 - SIDE_DEBOSS
    solid = None
    for depth, pts_yz in nested:
        body = cq.Workplane("YZ", origin=(x0, 0, 0)).polyline(pts_yz).close().extrude(SIDE_DEBOSS)
        if depth % 2 == 0:
            solid = body if solid is None else solid.union(body)
        elif solid is not None:
            solid = solid.cut(body)
    return solid


SENSOR_NAMES = ("+5V", "+24V", "mA", "10V", "IO1", "IO2", "IO3", "IO4", "GND", "GND")
SENSOR_NOTES = ("5V 600mA", "VIN PASS", "4-20mA LOOP", "0-5V / 0-10V", "ECHO / SDA / RX", "TRIG / SCL / TX",
                "GEIGER PULSE", "METER PULSE", "", "")


def sensor_pole_z():
    """Enclosure z of the 10 sensor poles in order: J2 1..4, J5 1..3, J6 1..3 (spec terminals.sensor_io.refs)."""
    zs = []
    for ref in SPEC["terminals"]["sensor_io"]["refs"]:
        by_pin = _pin_z_positions(ref)
        zs += [by_pin[k] for k in sorted(by_pin, key=int)]
    return zs


def side_wall_legend_bodies():
    """Debossed terminal pole numbers, signal names and short vertical
    explanations under each sensor pole, and the schematic changeover relay
    symbol over NC/COM/NO on the right side wall (x = +WIDTH/2) of the base."""
    items = []
    # 1. Top edge: sensor pole numbers (1..10) and signal names right under the wire entries
    for pole, (z_c, name) in enumerate(zip(sensor_pole_z(), SENSOR_NAMES), start=1):
        items.append(_side_text_solid(str(pole), z_c, 77.2, 1.8))
        items.append(_side_text_solid(name, z_c, 74.5, 1.0))

    # 2. Short leader under each signal name, then its explanation reading upwards
    for z_c, note in zip(sensor_pole_z(), SENSOR_NOTES):
        if not note:
            continue
        items.append(_side_line(z_c, 73.6, z_c, 72.4, lw=0.24))
        items.append(_side_text_vertical(note, z_c, 71.8, 1.0))

    j1_z = _pin_z_positions("J1")
    j4_z = _pin_z_positions("J4")
    j1_names = {"1": "GND", "2": "VIN"}
    j4_names = dict(zip(("1", "2", "3"), SPEC["terminals"]["relay_out"]["labels"]))

    # 3. Bottom edge: J1 (1=GND, 2=VIN with 9-30VDC above it) and J4 (labels from spec.yaml)
    for pin, z_c in sorted(j1_z.items()):
        items.append(_side_text_solid(pin, z_c, 3.6, 2.0))
        items.append(_side_text_solid(j1_names[pin], z_c, 6.4, 1.2))
    z_vin = j1_z["2"]
    items.append(_side_line(z_vin, 8.2, z_vin, 12.4, lw=0.26))
    items.append(_side_text_solid("9-30VDC", z_vin, 14.8, 1.2, align="center"))

    for pin, z_c in sorted(j4_z.items()):
        items.append(_side_text_solid(pin, z_c, 3.6, 2.0))
        items.append(_side_text_solid(j4_names[pin], z_c, 6.4, 1.2))

    # 4. Changeover symbol over J4: COM pivot, wiper resting on NC (de-energised), NO open
    pin_of = {name: pin for pin, name in j4_names.items()}
    z_com, z_no, z_nc = (j4_z[pin_of[n]] for n in ("COM", "NO", "NC"))
    toward_com_no = math.copysign(1.4, z_com - z_no)
    items.append(_side_line(z_no, 8.2, z_no, 11.0, lw=0.26))
    items.append(_side_line(z_no, 11.0, z_no + toward_com_no, 11.0, lw=0.26))
    items.append(_side_dot(z_no + toward_com_no, 11.0, radius=0.40))
    items.append(_side_line(z_nc, 8.2, z_nc, 13.0, lw=0.26))
    items.append(_side_line(z_nc, 13.0, z_no, 13.0, lw=0.26))
    items.append(_side_dot(z_no, 13.0, radius=0.40))
    items.append(_side_line(z_com, 8.2, z_com, 10.0, lw=0.26))
    items.append(_side_dot(z_com, 10.0, radius=0.45))
    items.append(_side_line(z_com, 10.0, z_no, 12.8, lw=0.30))
    # Rating label above the symbol (Omron G6B-2114P, 230 VAC load circuit fused <= 2 A)
    items.append(_side_text_solid("230VAC 2A", z_no, 15.4, 1.2, align="center"))

    combined = items[0]
    for s in items[1:]:
        if s is not None:
            combined = combined.union(s)
    return combined


def build_base():
    shell = box(-WIDTH / 2, WIDTH / 2, 0, HIDDEN_H, 0, BASE_TOP_Z).cut(
        box(-INNER_W / 2, INNER_W / 2, WALL, HIDDEN_H - WALL, WALL, BASE_TOP_Z + 1))
    base = shell.union(rail_blocks())
    pocket, latch = latch_parts()
    base = base.cut(pocket).union(latch)
    for slot in terminal_slots():
        base = base.cut(box(slot["x0"], slot["x1"], slot["y0"], slot["y1"], slot["z0"], slot["z1"]))
    # Open the left side wall so the vertical main board slides in from the left (-x -> +x)
    base = base.cut(box(-WIDTH / 2 - 1, -INNER_W / 2 + 0.01, WALL, HIDDEN_H - WALL, WALL, BASE_TOP_Z + 1))
    for body in leg_bodies() + capacitor_cradles():
        base = base.union(walls_clip(body))
    for keeper in shoulder_snap_keepers():
        base = base.cut(keeper)
    # Deboss the terminal pole numbers, names, and wiring legend into the right side wall
    base = base.cut(side_wall_legend_bodies())
    return base


def peg_bodies():
    return [cylinder(p["x"], p["y"], MAIN_Z, SHOULDER_Z[shoulder_of(p["y"])] - WALL, PEG_DIAMETER)
            for p in pegs()]


def standoff_bodies():
    """Columns from the front wall onto the UI board front, between the buttons
    and the OLED panel (the snap hooks hold the board from behind)."""
    return [cylinder(p["x"], p["y"], UI_BOARD_TOP_Z, FRONT_INNER_Z + 0.01, STANDOFF_DIAMETER) for p in standoffs()]


def ui_rib_bodies():
    """Locating ribs on the protrusion's inner walls around the UI board edges
    (UI_RIB['gap'] per side), so buttons/LEDs stay within 0.3 mm of their windows."""
    half_w = UI_W / 2
    ui = board_slabs("ui")
    y_lo, y_hi = min(s["y0"] for s in ui), max(s["y1"] for s in ui)
    z0, z1 = UI_BOARD_Z - 0.6, UI_BOARD_TOP_Z + 0.6
    ribs = []
    for y in UI_RIB["side_ys"]:
        for s in (-1, 1):
            ribs.append(box(*sorted((s * (half_w + UI_RIB["gap"]), s * (INNER_W / 2 + 0.01))),
                            y - UI_RIB["len"] / 2, y + UI_RIB["len"] / 2, z0, z1))
    for x in UI_RIB["end_xs"]:
        w = UI_RIB["end_w"] / 2
        ribs.append(box(x - w, x + w, FRONT_Y_START + WALL - 0.01, y_lo - UI_RIB["gap"], z0, z1))
        ribs.append(box(x - w, x + w, y_hi + UI_RIB["gap"], FRONT_Y_END - WALL + 0.01, z0, z1))
    return ribs


def button_top_z(ref):
    return UI_BOARD_TOP_Z + components("ui")[ref]["height"]


def button_tab_outline(hole, grow=0.0):
    """Front outline of a C-shaped button tab (or of its slot with grow =
    slot): pad circle (x, y, d) and arm box (x0, x1, y0, y1) towards the
    centre bridge. The left tab reads as a C, the right one as a mirrored C."""
    t = BUTTON_TAB
    root = math.copysign(t["root_x"], hole["x"])
    return ((hole["x"], hole["y"], t["pad"] + 2 * grow),
            (*sorted((hole["x"], root)), hole["y"] - t["arm"] / 2 - grow, hole["y"] + t["arm"] / 2 + grow))


def button_tab(ref, hole):
    """C-slot + thinning (cuts) and plunger + front bump (bodies) for one button."""
    t = BUTTON_TAB

    def solid(grow, z0, z1):
        (cx, cy, d), (x0, x1, y0, y1) = button_tab_outline(hole, grow)
        return cylinder(cx, cy, z0, z1, d).union(box(x0, x1, y0, y1, z0, z1))

    through = (FRONT_INNER_Z - 1, TOTAL_D + 1)
    tab_back = TOTAL_D - t["thickness"]
    slot = solid(t["slot"], *through).cut(solid(0.0, *through))
    thin = solid(0.0, FRONT_INNER_Z - 1, tab_back)
    bump = cylinder(hole["x"], hole["y"], TOTAL_D - 0.01, TOTAL_D + t["boss_height"], t["boss"]) \
        .faces(">Z").edges().fillet(t["boss_round"])
    plunger = cylinder(hole["x"], hole["y"], button_top_z(ref) + t["nub_gap"], tab_back + 0.01, t["nub"])
    return [slot, thin], [plunger, bump]


def button_flexures():
    cuts, bodies = [], []
    for name, hole in button_holes().items():
        c, b = button_tab("SW1" if name == "PROG" else "SW2", hole)
        cuts += c
        bodies += b
    return cuts, bodies


def baffle_bodies():
    outer = LED_WINDOW + 2 * BAFFLE_WALL
    return [cylinder(w["x"], w["y"], STACK.baffle_bottom_z, FRONT_INNER_Z + 0.01, outer)
            .cut(cylinder(w["x"], w["y"], STACK.baffle_bottom_z - 1, FRONT_INNER_Z + 1, LED_WINDOW))
            for w in led_windows()]


def snap_geometry():
    z_free = UI_BOARD_Z - SNAP["free_end_below_board"]
    z_root = FRONT_INNER_Z - 0.4
    half, s = SNAP["width"] / 2, SNAP["slot"]
    x_hook = UI_W / 2 - SNAP["overlap"]
    parts = []
    for y in SNAP["y"]:
        for side in (1, -1):
            wall = sorted((side * INNER_W / 2, side * WIDTH / 2))
            slot = box(wall[0] - 0.01, wall[1] + 0.01, y - half - s, y + half + s, z_free - s, z_root)
            tongue = box(*wall, y - half, y + half, z_free, z_root + 0.01)
            hook = box(*sorted((side * x_hook, side * INNER_W / 2)), y - half, y + half,
                       UI_BOARD_Z - SNAP["hook_height"], UI_BOARD_Z)
            ramp_edge = "|Y and <Z and " + ("<X" if side > 0 else ">X")
            parts.append((slot, tongue.union(hook.edges(ramp_edge).chamfer(SNAP["overlap"] + 0.3))))
    return parts


def snap_bodies():
    return [tongue for _, tongue in snap_geometry()]


def lip_bodies():
    """Locating lip along the base's right wall, stopped short of the
    terminal blocks that reach up to the shoulder at both ends."""
    x_out = INNER_W / 2 - 0.15
    z0 = BASE_TOP_Z - LIP["depth"]
    terms = [p for p in part_boxes() if p["board"] == "main" and p["ref"] in ("J1", "J2", "J4", "J5", "J6")]
    y_lo = max([p["y1"] for p in terms if p["y0"] < HIDDEN_H / 2] + [WALL + 1]) + FDM_CLEAR
    y_hi = min([p["y0"] for p in terms if p["y0"] > HIDDEN_H / 2] + [HIDDEN_H - WALL - 1]) - FDM_CLEAR
    return [box(*sorted((x_out, x_out - LIP["thickness"])), y_lo, y_hi, z0, BASE_TOP_Z)]


def shoulder_plate(side):
    face = SHOULDER_Z[side]
    y0, y1 = (0, FRONT_Y_START) if side == "bottom" else (FRONT_Y_END, HIDDEN_H)
    inner_y = (WALL, FRONT_Y_START + 1) if side == "bottom" else (FRONT_Y_END - 1, HIDDEN_H - WALL)
    shell = box(-WIDTH / 2, WIDTH / 2, y0, y1, BASE_TOP_Z, face)
    return shell.cut(box(-INNER_W / 2, INNER_W / 2, *inner_y, BASE_TOP_Z - 1, face - WALL))


def build_cover():
    protrusion = box(-WIDTH / 2, WIDTH / 2, FRONT_Y_START, FRONT_Y_END, BASE_TOP_Z, TOTAL_D).cut(
        box(-INNER_W / 2, INNER_W / 2, FRONT_Y_START + WALL, FRONT_Y_END - WALL, BASE_TOP_Z - 1, FRONT_INNER_Z))
    cover = protrusion.union(shoulder_plate("bottom")).union(shoulder_plate("top"))
    # left side wall: FDM_CLEAR to the base's top/bottom walls and floor
    cover = cover.union(box(-WIDTH / 2, -INNER_W / 2, WALL + FDM_CLEAR, HIDDEN_H - WALL - FDM_CLEAR,
                            WALL + FDM_CLEAR, BASE_TOP_Z + 0.01))
    for body in (lip_bodies() + peg_bodies() + standoff_bodies() + screw_tab_bodies() + baffle_bodies()
                 + slot_filler_bodies() + ui_rib_bodies()):
        cover = cover.union(body)
    for pocket in tht_tail_recesses():
        cover = cover.cut(pocket)
    for slot, tongue in snap_geometry():
        cover = cover.cut(slot).union(tongue)
    front = (FRONT_INNER_Z - 1, TOTAL_D + 1)
    for w in led_windows():
        cover = cover.cut(cylinder(w["x"], w["y"], FRONT_INNER_Z - 1, TOTAL_D - STACK.led_skin_mm, LED_WINDOW))
    win, panel = oled_window(), oled_panel_real()
    cover = cover.cut(box(win["cx"] - win["w"] / 2, win["cx"] + win["w"] / 2,
                          win["cy"] - win["h"] / 2, win["cy"] + win["h"] / 2, *front))
    m = OLED_POCKET_MARGIN
    cover = cover.cut(box(panel["cx"] - panel["w"] / 2 - m, panel["cx"] + panel["w"] / 2 + m,
                          panel["cy"] - panel["h"] / 2 - m, panel["cy"] + panel["h"] / 2 + m,
                          FRONT_INNER_Z - 1, FRONT_INNER_Z + OLED_POCKET_DEPTH))
    cuts, nubs = button_flexures()
    for c in cuts:
        cover = cover.cut(c)
    for n in nubs:
        cover = cover.union(n)
    return cover


def export_parts(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, part in (("base", build_base()), ("cover", build_cover())):
        cq.exporters.export(part, str(out_dir / f"{name}.step"), cq.exporters.ExportTypes.STEP)
        cq.exporters.export(part, str(out_dir / f"{name}.stl"), cq.exporters.ExportTypes.STL)
        print(f"{name}: {name}.step + {name}.stl")


if __name__ == "__main__":
    export_parts(sys.argv[1] if len(sys.argv) > 1 else REPO / "mechanical/build" / SPEC["active_variant"])
