"""CadQuery 1-DIN (18 mm) side-opening enclosure for the Universal Sensor Node.

base   rail side, z -5..shoulder: a TS35 channel in the 5 mm deep back
       (EN 60715: 35 +-0.3 between lips, 1 mm lips) with a fixed hook under
       the top lip and a sprung sliding latch under the bottom lip. Open on
       the left side (-x) so the vertical main board slides straight in.
       Top wall has openings for J2, J3, J4 (6-pole sensor bank); bottom wall
       has openings for J1, J5 (4-pole power + expansion I/O bank).
cover  front side + left side wall: shoulder plates, front protrusion (0.96"
       64x128 OLED window + backing rails, button holes, LED baffle windows),
       and four side snap-click hooks that lock into the base.
"""

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
    oled_glass,
    oled_module,
    oled_panel,
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
STANDOFF_DIAMETER = 3.0
LED_WINDOW = 2.2
BAFFLE_WALL = 0.4
BUTTON_HOLE = 2.6
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


def shoulder_snap_bodies():
    """Four side snap-click hooks on the cover locking into the base."""
    if screw_tabs():
        return []
    bodies = []
    for y_c in (15.6, 63.8):
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
               for y_c in (15.6, 63.8)]
    keepers += [box(-INNER_W / 2 - 0.1, -INNER_W / 2 + 1.3, WALL - 0.6, WALL + 0.1, 8.8, 14.2),
                box(-INNER_W / 2 - 0.1, -INNER_W / 2 + 1.3, HIDDEN_H - WALL - 0.1, HIDDEN_H - WALL + 0.6, 8.8, 14.2)]
    return keepers


def screw_tab_bodies():
    return list(shoulder_snap_bodies())


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


def side_wall_legend_bodies():
    """Debossed/embossed terminal pole numbers, signal names, 90-deg leader lines
    to left-aligned signal explanations, and schematic changeover relay symbol
    over NC/COM/NO on the right side wall (x = +WIDTH/2) of the base."""
    j2_raw = _pin_z_positions("J2")
    j5_raw = _pin_z_positions("J5")
    j2_z = {
        "1": j2_raw["1"],
        "2": j2_raw["2"],
        "3": j2_raw["3"],
        "4": j2_raw["4"],
        "5": j5_raw["1"],
        "6": j5_raw["2"],
        "7": j5_raw["3"],
    }
    j1_z = _pin_z_positions("J1")
    j4_z = _pin_z_positions("J4")

    j2_names = {"1": "GND", "2": "+5V", "3": "+24V", "4": "mA", "5": "10V", "6": "IO1", "7": "IO2"}
    j1_names = {"1": "GND", "2": "VIN"}
    j4_names = {"1": "NC", "2": "COM", "3": "NO"}

    items = []
    # 1. Top edge: J2 pole numbers (1..7) and signal names right under the top wire entries
    for pin, z_c in sorted(j2_z.items()):
        items.append(_side_text_solid(pin, z_c, 77.2, 2.0))
        items.append(_side_text_solid(j2_names[pin], z_c, 74.3, 1.1))

    # 2. Thin 90-degree L-shaped leader lines from J2 pins 3 (+24V), 4 (mA), 5 (10V), 6 (IO1), 7 (IO2)
    #    with compact vertical row spacing, turning right (-z) to left-aligned explanation text.
    z_elbow_end = 13.4
    z_text_left = 12.6
    callouts = (
        ("3", 65.3, "VIN PASS"),
        ("4", 62.4, "4-20mA LOOP"),
        ("5", 59.5, "0-5V / 0-10V"),
        ("6", 56.6, "SDA / RX / PLS"),
        ("7", 53.7, "SCL / TX / TRIG"),
    )
    for pin, y_row, desc in callouts:
        zp = j2_z[pin]
        items.append(_side_line(zp, 72.5, zp, y_row, lw=0.24))
        items.append(_side_line(zp, y_row, z_elbow_end, y_row, lw=0.24))
        items.append(_side_text_solid(desc, z_text_left, y_row, 1.15, align="left"))

    # 3. Bottom edge: J1 (1=GND, 2=VIN with 9-30VDC above it) and J4 (1=NC, 2=COM, 3=NO)
    for pin, z_c in sorted(j1_z.items()):
        items.append(_side_text_solid(pin, z_c, 3.6, 2.0))
        items.append(_side_text_solid(j1_names[pin], z_c, 6.4, 1.2))
    z_vin = j1_z["2"]
    items.append(_side_line(z_vin, 8.2, z_vin, 12.4, lw=0.26))
    items.append(_side_text_solid("9-30VDC", z_vin, 14.8, 1.2, align="center"))

    for pin, z_c in sorted(j4_z.items()):
        items.append(_side_text_solid(pin, z_c, 3.6, 2.0))
        items.append(_side_text_solid(j4_names[pin], z_c, 6.4, 1.2))

    # 4. Compact schematic changeover relay symbol directly over J4's NC (pin 1), COM (pin 2), NO (pin 3)
    z_nc, z_com, z_no = j4_z["1"], j4_z["2"], j4_z["3"]
    # NC leg: short vertical up from y=8.2 to y=12.4 + horizontal fixed contact bar toward COM
    items.append(_side_line(z_nc, 8.2, z_nc, 12.4, lw=0.26))
    items.append(_side_line(z_nc, 12.4, z_nc - 1.4, 12.4, lw=0.26))
    items.append(_side_dot(z_nc - 1.4, 12.4, radius=0.40))
    # NO leg: short vertical up from y=8.2 to y=12.4 + horizontal open contact bar toward COM
    items.append(_side_line(z_no, 8.2, z_no, 12.4, lw=0.26))
    items.append(_side_line(z_no, 12.4, z_no + 1.4, 12.4, lw=0.26))
    items.append(_side_dot(z_no + 1.4, 12.4, radius=0.40))
    # COM leg: short vertical up from y=8.2 to pivot dot at y=10.0 + diagonal wiper arm touching NC
    items.append(_side_line(z_com, 8.2, z_com, 10.0, lw=0.26))
    items.append(_side_dot(z_com, 10.0, radius=0.45))
    items.append(_side_line(z_com, 10.0, z_nc - 1.1, 12.8, lw=0.30))
    # Centered rating label above the relay symbol
    items.append(_side_text_solid("250VAC 2A", z_com, 14.8, 1.2, align="center"))

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
    for slot in wire_entries():
        if slot.get("side") == "bottom":
            base = base.cut(box(slot["x0"], slot["x1"], -1, WALL + 1, slot["z0"], slot["z1"]))
        else:
            base = base.cut(box(slot["x0"], slot["x1"], HIDDEN_H - WALL - 1, HIDDEN_H + 1, slot["z0"], slot["z1"]))
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
    z1 = FRONT_INNER_Z + STACK.pocket_depth + 0.1
    bodies = [cylinder(p["x"], p["y"], UI_BOARD_TOP_Z, z1, STANDOFF_DIAMETER) for p in standoffs()]
    z_tape = STACK.oled_glass_z - STACK.oled["panel"] - STACK.oled["module_board"] - 1.5 if hasattr(STACK, "oled") else FRONT_INNER_Z - 1.5
    for sx in (-6.3, 6.3):
        bodies.append(box(sx - 0.7, sx + 0.7, 31.8, 56.5, z_tape, z1))
    for sx in (-5.8, 5.8):
        bodies.append(box(sx - 1.1, sx + 1.1, 30.85, 31.65, z_tape, z1))
    return bodies


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
    x_out = INNER_W / 2 - 0.15
    z0 = BASE_TOP_Z - LIP["depth"]
    lips = [box(*sorted((x_out, x_out - LIP["thickness"])), WALL + 1, HIDDEN_H - WALL - 1, z0, BASE_TOP_Z)]
    return lips


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
    cover = cover.union(box(-WIDTH / 2, -INNER_W / 2, WALL - 0.01, HIDDEN_H - WALL + 0.01, WALL, BASE_TOP_Z + 0.01))
    for body in lip_bodies() + peg_bodies() + standoff_bodies() + screw_tab_bodies() + baffle_bodies():
        cover = cover.union(body)
    for slot, tongue in snap_geometry():
        cover = cover.cut(slot).union(tongue)
    front = (FRONT_INNER_Z - 1, TOTAL_D + 1)
    for w in led_windows():
        cover = cover.cut(cylinder(w["x"], w["y"], FRONT_INNER_Z - 1, TOTAL_D - STACK.led_skin_mm, LED_WINDOW))
    for hole in button_holes().values():
        cover = cover.cut(cylinder(hole["x"], hole["y"], *front, BUTTON_HOLE))
    win, panel, module = oled_window(), oled_panel(), oled_module()
    cover = cover.cut(box(win["cx"] - win["w"] / 2, win["cx"] + win["w"] / 2,
                          win["cy"] - win["h"] / 2, win["cy"] + win["h"] / 2, *front))
    margin = 0.5
    pocket = box(module["cx"] - module["w"] / 2 - margin, module["cx"] + module["w"] / 2 + margin,
                 module["cy"] - module["h"] / 2 - margin, module["cy"] + module["h"] / 2 + margin,
                 FRONT_INNER_Z - 1, FRONT_INNER_Z + STACK.pocket_depth)
    if panel != oled_glass():
        g_margin = 0.25
        pocket = pocket.union(box(panel["cx"] - panel["w"] / 2 - g_margin, panel["cx"] + panel["w"] / 2 + g_margin,
                                  panel["cy"] - panel["h"] / 2 - g_margin, panel["cy"] + panel["h"] / 2 + g_margin,
                                  FRONT_INNER_Z - 1, TOTAL_D - 0.6))
    for body in standoff_bodies():
        pocket = pocket.cut(body)
    return cover.cut(pocket)


def export_parts(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, part in (("base", build_base()), ("cover", build_cover())):
        cq.exporters.export(part, str(out_dir / f"{name}.step"), cq.exporters.ExportTypes.STEP)
        cq.exporters.export(part, str(out_dir / f"{name}.stl"), cq.exporters.ExportTypes.STL)
        print(f"{name}: {name}.step + {name}.stl")


if __name__ == "__main__":
    export_parts(sys.argv[1] if len(sys.argv) > 1 else REPO / "mechanical/build" / SPEC["active_variant"])
