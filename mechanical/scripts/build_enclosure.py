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
    ui_to_enc,
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
# Printed in PA12 on MJF / SLS (powder bed). Gaps inside one printed part narrower than
# MIN_PRINT_GAP fuse; FDM_CLEAR is only used between separately printed parts or a part and a
# PCB / terminal body, which cannot fuse (see the release README, "Printing").
MIN_PRINT_GAP = 0.6
PART_AIR = 0.3     # air around every part body (supports stop closer: BOARD_SUPPORT_GAP)
FDM_CLEAR = 0.2    # per side, between printed parts and around PCB/terminal bodies
# C-shaped spring tab per button (same geometry as knx-dali-gateway v3): a
# round pad over the switch on an arm rooted at a shared centre bridge, both
# thinned to `thickness`; rounded bump on the front, plunger behind the pad.
BUTTON_TAB = {"pad": 2.6, "arm": 2.0, "root_x": 0.9, "slot": MIN_PRINT_GAP, "thickness": 0.7, "nub": 1.4,
              "nub_gap": 0.1, "boss": 2.0, "boss_height": 0.6, "boss_round": 0.25}
THT_TAIL = 2.5     # max solder-tail protrusion behind the main board (clip longer leads)
THT_RECESS = 1.0   # recess depth in the cover's left wall over THT tails
UI_RIB = {"gap": 0.15, "len": 3.0, "side_ys": (23.0, 40.5, 58.0), "end_xs": (-6.0, 6.0), "end_w": 1.5}
SCREW_HOLE = 3.2
CASE_SCREW = {"pilot": 2.2, "clearance": 2.8, "depth": 8.5, "z": BASE_TOP_Z - 2.0}
SCREW_TAB = {"width": 4.0, "depth": 8.5, "z0": 39.85}
LIP = {"thickness": 1.2, "depth": 2.0}
SNAP = {"overlap": 0.5, "width": 6.0, "slot": MIN_PRINT_GAP, "hook_height": 1.8, "free_end_below_board": 1.8,
        "y": (FRONT_Y_START + 12, FRONT_Y_END - 12)}

RAIL = {"centre": HIDDEN_H / 2, "slot": 35.4, "lip": 1.0, "clearance": 0.1}
BACK_DEPTH = 5.0
HOOK_REACH = 1.5
LATCH_MAX_STRAIN = 0.025  # PA12 flexure, repeated use
LATCH = {"half_width": 1.8 if WIDTH < 30 else 5.0, "tab_half_width": 3.0 if WIDTH < 30 else 5.0,
         "gap": 0.7, "tab_bottom": -6.0, "beam": 0.6, "y0": 3.0, "skin": 1.0, "hole": (3.0, 1.6),
         "hole_y": -4.0, "travel": HOOK_REACH + 0.3}
LATCH["reach"] = min(16.0, WIDTH / 2 - LATCH["skin"] - LATCH["gap"])


def latch_leg_length(latch=LATCH):
    """Free length of one spring leg between its two turns."""
    return latch["reach"] - (latch["half_width"] + latch["gap"]) - 2 * latch["beam"]


def latch_strain(legs, latch=LATCH):
    """Peak bending strain of a fixed-guided leg when the bar travels its full
    release travel, shared equally by `legs` legs in series: 3 t d / L^2."""
    return 3 * latch["beam"] * (latch["travel"] / legs) / latch_leg_length(latch) ** 2


LATCH["legs"] = next(n for n in range(1, 40, 2) if latch_strain(n) <= LATCH_MAX_STRAIN)


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
    """Sliding latch under the rail's bottom lip. A bar carries the lip at its
    top; its lower end is a wider tab below the case with a hole for a flat
    screwdriver. On each side of the bar a serpentine spring of LATCH["legs"]
    legs in series (enough that no leg bends past LATCH_MAX_STRAIN over the
    release travel) springs it back. Every gap is at least MIN_PRINT_GAP so a
    powder print does not fuse the latch to the case."""
    low, _ = rail_edges()
    back = -BACK_DEPTH
    w, g, b, n = LATCH["half_width"], LATCH["gap"], LATCH["beam"], LATCH["legs"]
    reach, pitch, y0 = LATCH["reach"], b + g, LATCH["y0"]
    y_last = y0 + (n - 1) * pitch
    pocket = box(-w - g, w + g, LATCH["tab_bottom"] - 1, low + 1, back - 1, 0).union(
        box(-reach - g, reach + g, y0 - LATCH["travel"] - g, y_last + b + g, back - 1, 0))
    bar_z = (back, -g)
    tw = LATCH["tab_half_width"]
    latch = box(-w, w, LATCH["tab_bottom"], low - g, *bar_z).union(
        box(-tw, tw, LATCH["tab_bottom"], -g, *bar_z))
    lip = box(-w, w, low - g, low + HOOK_REACH, *lip_z())
    latch = latch.union(lip.edges("|X and <Z and >Y").chamfer(1.0))
    x_in = w + g
    for s in (-1, 1):
        for i in range(n):
            y = y0 + i * pitch
            start = w if i == 0 else x_in
            end = reach + g + 0.5 if i == n - 1 else reach
            latch = latch.union(box(*sorted((s * start, s * end)), y, y + b, *bar_z))
            if i < n - 1:
                x_turn = (reach - b, reach) if i % 2 == 0 else (x_in, x_in + b)
                latch = latch.union(box(*sorted((s * x_turn[0], s * x_turn[1])), y, y + pitch + b, *bar_z))
    hole_w, hole_h = LATCH["hole"]
    hole = box(-hole_w / 2, hole_w / 2, LATCH["hole_y"] - hole_h / 2, LATCH["hole_y"] + hole_h / 2, back - 1, 1)
    return pocket, latch.cut(hole)


BOARD_SUPPORT_GAP = 0.1   # posts stop this short of the main board's front face (< PART_AIR)
POST_HALF = 1.0
POST_Z_MAX = 36.0         # below the lip, the right-wall snap keepers and the cover shoulder


def _yz_clear(boxes, y, z, half, air=PART_AIR):
    return all(y + half + air <= b["y0"] or y - half - air >= b["y1"] or
               z + half + air <= b["z0"] or z - half - air >= b["z1"] for b in boxes)


def front_posts():
    """(y, z) of the posts from the base's right wall to BOARD_SUPPORT_GAP short
    of the main board's front face: one per quadrant of the board, in columns
    free of parts over the whole depth (part bodies + PART_AIR), as far out
    as the free grid allows. The knx print had no support there and its
    tallest capacitor carried the board."""
    slab = board_slab("main")
    parts = [b for b in part_boxes() if b["board"] == "main"]
    y_mid, z_mid = (slab["y0"] + slab["y1"]) / 2, (slab["z0"] + slab["z1"]) / 2
    h, step = POST_HALF, 0.25
    cells = [(slab["y0"] + h + 0.5 + i * step, slab["z0"] + h + 0.5 + j * step)
             for i in range(int((slab["y1"] - slab["y0"] - 2 * h - 1) / step) + 1)
             for j in range(int((min(slab["z1"], POST_Z_MAX) - slab["z0"] - 2 * h - 1) / step) + 1)]
    free = [(y, z) for y, z in cells if _yz_clear(parts, y, z, h)]
    posts = []
    for qy in (False, True):
        for qz in (False, True):
            quad = [(y, z) for y, z in free if (y > y_mid) == qy and (z > z_mid) == qz]
            if not quad:
                raise ValueError(f"no part-free column for a main board support in quadrant {(qy, qz)}")
            posts.append(max(quad, key=lambda c: (c[0] - y_mid) ** 2 + (c[1] - z_mid) ** 2))
    return posts


def post_bodies():
    x0 = board_slab("main")["x1"] + BOARD_SUPPORT_GAP
    return [box(x0, INNER_W / 2 + 0.01, y - POST_HALF, y + POST_HALF, z - POST_HALF, z + POST_HALF)
            for y, z in front_posts()]


RIB = {"half_y": 0.4, "half_z": 1.5, "gap": 0.1, "max_spacing": 40.0, "rows": 3}


def main_ribs():
    """(y, z) of the ribs on the cover's left wall that back the main board:
    RIB["rows"] rows (the walls count as supports, so the spacing stays under
    RIB["max_spacing"]) of two ribs, each clear of every THT solder-tail
    recess (tht_tail_recesses) by PART_AIR. The cover slides on along +x, so a rib only sweeps the tail
    columns, which it avoids."""
    keep = []
    for pocket in tht_tail_recesses():
        bb = pocket.val().BoundingBox()
        keep.append({"y0": bb.ymin - PART_AIR, "y1": bb.ymax + PART_AIR, "z0": bb.zmin - PART_AIR, "z1": bb.zmax + PART_AIR})
    slab = board_slab("main")
    ribs = []
    for k in range(1, RIB["rows"] + 1):
        target = WALL + k * INNER_H / (RIB["rows"] + 1)
        for z_target in (slab["z0"] + (slab["z1"] - slab["z0"]) / 3, slab["z0"] + 2 * (slab["z1"] - slab["z0"]) / 3):
            spots = [(target + dy * 0.25, z_target + dz * 0.25) for dy in range(-40, 41) for dz in range(-30, 31)]
            spots = [(y, z) for y, z in spots if slab["y0"] + 1 < y < slab["y1"] - 1 and
                     _yz_clear(keep, y, z, max(RIB["half_y"], RIB["half_z"]), air=0.0)]
            if not spots:
                raise ValueError(f"no tail-free spot for a cover rib near y {target:.1f}")
            ribs.append(min(spots, key=lambda c: abs(c[0] - target) + abs(c[1] - z_target) / 4))
    return ribs


def rib_bodies():
    back = SPEC["boards"]["main"]["x"] - MAIN_THICK
    return [box(-INNER_W / 2 - 0.01, back - RIB["gap"], y - RIB["half_y"], y + RIB["half_y"],
                z - RIB["half_z"], z + RIB["half_z"]) for y, z in main_ribs()]


# Degson DG127R-5.08-03P (J4, 230 V relay output): M2.5 screws in the body's top face, which on
# the vertical main board faces the right wall; their axes sit at mid-depth of the 8.1 mm body
# (customer drawing rev D0). A hole through the right wall over each screw takes a 2.5 mm blade;
# the screw heads stay 1.5 mm inside the wall, beyond the reach of an IP20 test finger.
SCREW_REFS = ("J4",)
SCREW_ACCESS = {"axis_from_face": 4.05, "hole": 3.0}


def screw_holes():
    """Screwdriver holes through the base's right wall, one per screw of SCREW_REFS."""
    holes = []
    for ref in SCREW_REFS:
        body = next(b for b in part_boxes() if (b["board"], b["ref"]) == ("main", ref))
        y = body["y0"] + SCREW_ACCESS["axis_from_face"]
        for z in _pin_z_positions(ref).values():
            holes.append({"ref": ref, "y": y, "z": z, "d": SCREW_ACCESS["hole"], "body_x1": body["x1"]})
    return holes


def screw_hole_solid(hole):
    return (cq.Workplane("YZ").center(hole["y"], hole["z"]).circle(hole["d"] / 2)
            .extrude(WIDTH / 2 - INNER_W / 2 + 1.02).translate((INNER_W / 2 - 0.01, 0, 0)))


FLOOR_RELIEF = 0.6   # deepest recess into the 1.6 mm floor (1.0 mm stays)


def floor_reliefs():
    """Recesses in the base floor under part bodies that reach closer than
    PART_AIR to it: J4's datasheet body (Fab outline) overhangs the main
    board's rail-side edge and would sit 0.05 mm above the floor."""
    cuts = []
    for b in part_boxes():
        if b["board"] == "main" and b["z0"] < WALL + PART_AIR:
            z0 = b["z0"] - PART_AIR
            if z0 < WALL - FLOOR_RELIEF:
                raise ValueError(f"main {b['ref']} would leave less than {WALL - FLOOR_RELIEF} mm of floor")
            cuts.append(box(b["x0"] - PART_AIR, b["x1"] + PART_AIR, b["y0"] - PART_AIR, b["y1"] + PART_AIR,
                            z0, WALL + 0.01))
    return cuts


def leg_bodies():
    h = LEG_SIZE / 2
    return [box(p["x"] - h, p["x"] + h, p["y"] - h, p["y"] + h, WALL, MAIN_BOTTOM_Z) for p in legs()]


# Six side clicks: two on the right wall and a pair at each end of the left edge,
# so the cover cannot pivot about one edge (a four-click cover did on the knx print).
SIDE_SNAPS = {"right_y": (16.0, 63.8), "left_z": ((8.0, 13.0), (30.0, 35.0)), "half": 1.2}
SIDE_SNAP_YS = SIDE_SNAPS["right_y"]
SNAP_FREE = 0.6   # free gap each side of a right-wall snap tongue (lip notch)


def shoulder_snap_bodies():
    """Side snap-click hooks on the cover locking into the base."""
    if screw_tabs():
        return []
    bodies = []
    half = SIDE_SNAPS["half"]
    for y_c in SIDE_SNAPS["right_y"]:
        tongue = box(INNER_W / 2 - 1.1, INNER_W / 2, y_c - half, y_c + half, 39.2, BASE_TOP_Z + 0.4)
        barb = box(INNER_W / 2 - 1.1, INNER_W / 2 + 0.5, y_c - half, y_c + half, 39.2, 40.4)
        bodies.append(tongue.union(barb))
    for y_wall, d in ((WALL, 1), (HIDDEN_H - WALL, -1)):
        y0, y1 = sorted((y_wall, y_wall + d * 1.1))
        yb0, yb1 = sorted((y_wall - d * 0.5, y_wall + d * 1.1))
        for z0, z1 in SIDE_SNAPS["left_z"]:
            tongue = box(-WIDTH / 2, -INNER_W / 2 + 1.2, y0, y1, z0, z1)
            barb = box(-INNER_W / 2, -INNER_W / 2 + 1.2, yb0, yb1, z0, z1)
            bodies.append(tongue.union(barb))
    return bodies


def shoulder_snap_keepers():
    if screw_tabs():
        return []
    half = SIDE_SNAPS["half"] + 0.2
    keepers = [box(INNER_W / 2 - 0.1, INNER_W / 2 + 0.6, y_c - half, y_c + half, 39.0, 40.6)
               for y_c in SIDE_SNAPS["right_y"]]
    for z0, z1 in SIDE_SNAPS["left_z"]:
        keepers += [box(-INNER_W / 2 - 0.1, -INNER_W / 2 + 1.3, WALL - 0.6, WALL + 0.1, z0 - 0.2, z1 + 0.2),
                    box(-INNER_W / 2 - 0.1, -INNER_W / 2 + 1.3, HIDDEN_H - WALL - 0.1, HIDDEN_H - WALL + 0.6,
                        z0 - 0.2, z1 + 0.2)]
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


def _pin_z_positions(ref):
    """Map pin_number -> enclosure z coordinate for a terminal block on main."""
    comp = components("main")[ref]
    by_pin = {}
    for px, py, num in comp["pads"]:
        _, _, ez = board_point("main", px, py)
        by_pin.setdefault(str(num), []).append(ez)
    return {k: sum(v) / len(v) for k, v in by_pin.items()}


def sensor_pole_z():
    """Enclosure z of the 10 sensor poles in order: J2 1..4, J5 1..3, J6 1..3 (spec terminals.sensor_io.refs)."""
    zs = []
    for ref in SPEC["terminals"]["sensor_io"]["refs"]:
        by_pin = _pin_z_positions(ref)
        zs += [by_pin[k] for k in sorted(by_pin, key=int)]
    return zs


def side_wall_legend_bodies():
    """The right-side engraving (side_legend_cuts) as one solid, for the wall-mount box."""
    cuts = side_legend_cuts()
    combined = cuts[0]
    for cut in cuts[1:]:
        combined = combined.union(cut)
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
    for body in leg_bodies() + capacitor_cradles() + post_bodies():
        base = base.union(walls_clip(body))
    for keeper in shoulder_snap_keepers():
        base = base.cut(keeper)
    for hole in screw_holes():
        base = base.cut(screw_hole_solid(hole))
    for cut in floor_reliefs():
        base = base.cut(cut)
    for cut in side_legend_cuts():
        base = base.cut(cut)
    return base


def side_legend_cuts():
    """Connector and pole names (front_legend.side_labels) engraved INLAY_DEPTH
    into the base's right side face, beside the terminals."""
    import front_legend
    import legend_engraving
    return [legend_engraving.inlay(label.path(), 0.0).rotate((0, 0, 0), (0, 1, 0), 90).translate((WIDTH / 2, 0, 0))
            for label in front_legend.side_labels()]


def peg_bodies():
    return [cylinder(p["x"], p["y"], MAIN_Z, SHOULDER_Z[shoulder_of(p["y"])] - WALL, PEG_DIAMETER)
            for p in pegs()]


UI_EDGE_STOP = {"overlap": 0.4, "board_y": (0.6, 7.0)}


def ui_edge_stops():
    """Columns from the front wall onto the UI board's side edges beside the LED
    row, UI_EDGE_STOP["overlap"] onto the board (inside its 0.3 mm copper-free edge
    plus the LED courtyards' clearance): with the buttons lying above the LEDs there
    is no room for standoffs, and something must hold the board's lower end off the
    button tabs and LED baffles."""
    half = UI_W / 2
    y0, y1 = (ui_to_enc(0, y)[1] for y in UI_EDGE_STOP["board_y"])
    return [box(*sorted((s * (half - UI_EDGE_STOP["overlap"]), s * (INNER_W / 2 + 0.01))), y0, y1,
                UI_BOARD_TOP_Z, FRONT_INNER_Z + 0.01) for s in (-1, 1)]


def standoff_bodies():
    """Columns from the front wall onto the UI board front (the snap hooks hold
    the board from behind): layout standoffs plus the edge stops."""
    return [cylinder(p["x"], p["y"], UI_BOARD_TOP_Z, FRONT_INNER_Z + 0.01, STANDOFF_DIAMETER)
            for p in standoffs()] + ui_edge_stops()


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


LIP_BOND = {"over_wall": 0.6, "height": 1.2}


def lip_bodies():
    """Locating lip along the base's right wall. It hangs 0.15 mm inside the
    base wall, so a LIP_BOND bridge on top ties it into the cover's side wall
    along its whole length (the knx print's lip was held only where it
    crossed the snap tongues, which also locked them). Notched SNAP_FREE
    clear of each right-wall snap tongue, and at part bodies."""
    x_out = INNER_W / 2 - 0.15
    z0 = BASE_TOP_Z - LIP["depth"]
    top = BASE_TOP_Z + LIP_BOND["height"]
    terms = [p for p in part_boxes() if p["board"] == "main" and p["ref"] in ("J1", "J2", "J4", "J5", "J6")]
    y_lo = max([p["y1"] for p in terms if p["y0"] < HIDDEN_H / 2] + [WALL + 1]) + FDM_CLEAR
    y_hi = min([p["y0"] for p in terms if p["y0"] > HIDDEN_H / 2] + [HIDDEN_H - WALL - 1]) - FDM_CLEAR
    lip = box(x_out - LIP["thickness"], x_out, y_lo, y_hi, z0, BASE_TOP_Z).union(
        box(x_out - LIP["thickness"], INNER_W / 2 + LIP_BOND["over_wall"], y_lo, y_hi, BASE_TOP_Z - 0.01, top))
    free = SIDE_SNAPS["half"] + SNAP_FREE
    notches = [box(-WIDTH / 2, WIDTH / 2, y - free, y + free, z0 - 1, top + 1) for y in SIDE_SNAPS["right_y"]]
    reach = x_out - LIP["thickness"] - PART_AIR
    notches += [box(b["x0"] - PART_AIR, b["x1"] + PART_AIR, b["y0"] - PART_AIR, b["y1"] + PART_AIR, z0 - 1, top + 1)
                for b in part_boxes() if b["board"] == "main" and b["z1"] > z0 and b["x1"] > reach]
    for notch in notches:
        lip = lip.cut(notch)
    return [lip]


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
                 + slot_filler_bodies() + ui_rib_bodies() + rib_bodies()):
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
