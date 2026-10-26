"""Optical dial reader housing: a lock ring that twist-locks onto a meter dial's
clear hooks and presses down a carrier holding the `reader` PCB. The carrier
is a plain cylinder that stands on the glass inside the hooks, so the ring
drops straight over it; the ring's spring fingers press on the lid rim and the
carrier can still be turned inside the ring, so the sensor can be swung exactly over the
reflective wheel after the ring is locked. Works for any dial with a metal
half-disc/pointer under flat glass and hooks like these; fitted first to a
B METERS GMDM dial (water), where the IWM-PL3 module would go.

Dial coordinates: origin = dial centre on the glass top, z up, +x towards the
reflective wheel. Measured on the user's GMDM dial (calipers, 2026-10-24):
  - white rotating ring (the 360 deg lid) inner diameter 62.5 mm: only cleared
  - three clear hooks at 180, +60 and -60 deg from the wheel (49.9 mm wheel to
    far hook, 55.3 mm across two hooks' outer corners): 10.5 mm long, 3.3 mm
    deep, 4 mm tall, 1.5 mm from the white ring (outer face r = 29.75 mm); a
    1.5 mm deep notch starts 2 mm below the top, leaving a 2 mm catch lip
  - wheel axis 20.5 mm from the centre, half-disc diameter 14.5 mm, flat glass
  - lock direction: counter-clockwise seen from above
Outputs under hardware/releases/v1/accessories/dial_reader/.
"""

import json
import math
from pathlib import Path

import cadquery as cq

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "hardware/releases/v1/accessories/dial_reader"
RENDERS = OUT / "renders"
COMPONENTS = REPO / "hardware/build/v1/reader/components_reader.json"
PLAN_OFFSET = (10.5, 9.0)               # layout_reader.yaml plan coords = dial coords + this

# --- dial (measured) ---
RING_ID = 62.5
HOOK_ANGLES = (180.0, 60.0, -60.0)
HOOK_R_OUT = RING_ID / 2 - 1.5          # 29.75
HOOK_DEPTH = 3.3
HOOK_R_IN = HOOK_R_OUT - HOOK_DEPTH     # 26.45
HOOK_LEN = 10.5
HOOK_H = 4.0
LIP_H = 2.0
NOTCH_DEPTH = 1.5
WHEEL_X = 20.5
WHEEL_D = 14.5

CLEAR = 0.2                             # FDM sliding clearance per side

# --- reader PCB (dial coordinates) ---
PCB_X0, PCB_X1 = -PLAN_OFFSET[0], 31.5 - PLAN_OFFSET[0]   # -10.5 .. 21.0
PCB_Y = 9.0                                               # +-9
PCB_T = 1.2
PCB_Z = 7.5                             # PCB bottom: the 7.0 mm TCRT5000 ends 0.5 mm above the glass
PART_TOP = PCB_Z + PCB_T + 2.7          # tallest front part: WAGO 2059 terminal

# --- carrier: stands on the glass inside the hooks, turns freely ---
CARRIER_R_IN = 24.4
CARRIER_R_LOW = HOOK_R_IN - 0.45        # 26.0 below the hook tops: centred by the hooks, clears them all round
LID_Z = PART_TOP + 0.4                  # 11.8: carrier lid underside
LID_R = CARRIER_R_LOW                   # the closed carrier is one cylinder: the ring drops over it
LID_T = 1.6
RAIL_Z = 5.0                            # PCB pocket floor rails start
BOSS_ANGLES = (90.0, 217.0, 323.0)      # outside the PCB rectangle (webs >= 2.2 mm from its corners)
BOSS_R = 22.4
BOSS_D = 4.6
SCREW_PILOT = 1.7                       # M2 x 6 self-tapping
POSTS = ((19.5, 6.4), (19.5, -6.4), (-9.0, 7.0), (-9.0, -7.0))   # press the PCB, clear of parts

# --- lock ring ---
SKIRT_R_OUT = RING_ID / 2 - 0.25        # 31.0
SKIRT_R_IN = HOOK_R_OUT + CLEAR         # 29.95
TAB_REACH = 1.2
TAB_LEN = 6.0
TAB_TOP = HOOK_H - LIP_H - 0.3          # 1.7
RIB_W = 2.0
LOCK_TURN = 22.0
FLANGE_Z0 = LID_Z + LID_T + 0.4         # 13.8: above the lid's top face
RING_TOP = FLANGE_Z0 + 1.4              # 15.2
FLANGE_R_IN = 24.6                      # over the lid's outer rim (screw heads end at r 24.4)
BUMP_R = (FLANGE_R_IN + LID_R) / 2      # 25.3: bumps land on the lid rim
FINGER_ANGLES = (30.0, 90.0, 150.0, 210.0, 270.0, 330.0)
FINGER_SPAN = 30.0                      # deg: 14.6 mm cantilevers
FINGER_R_OUT = 29.0
SLOT = 0.6
BUMP_DROP = 1.3                         # 0.9 mm into the lid rim at rest, ~0.6 mm when the tabs bear on the lips

# Through the carrier lid (dial coordinates)
CABLE_XY = (-13.2, 0.0)                 # above the WAGO wire entries (wires bend up past the board edge)
CABLE_HOLE = (5.5, 9.0)
LED_XY = (16.0 - PLAN_OFFSET[0], 15.5 - PLAN_OFFSET[1])
TRIM_XY = (12.2 - PLAN_OFFSET[0], 9.0 - PLAN_OFFSET[1])
LED_FUNNEL_R = 2.4                      # top of the LED window
LED_RING_R = 3.4
LED_RING_H = 0.8
SET_XY = (TRIM_XY[0] - 5.0, TRIM_XY[1])  # label left of the trimmer hole
SET_DEPTH = 0.4


def polar(r, deg):
    a = math.radians(deg)
    return r * math.cos(a), r * math.sin(a)


def annulus(r_out, r_in, z0, z1):
    return cq.Workplane("XY").workplane(offset=z0).circle(r_out).circle(r_in).extrude(z1 - z0)


def sector(r_in, r_out, a0, a1, z0, z1, steps=24):
    """Annular sector between angles a0..a1 (deg)."""
    pts = [polar(r_out, a0 + (a1 - a0) * i / steps) for i in range(steps + 1)]
    pts += [polar(r_in, a1 - (a1 - a0) * i / steps) for i in range(steps + 1)]
    return cq.Workplane("XY").workplane(offset=z0).polyline(pts).close().extrude(z1 - z0)


def arc_block(r_in, r_out, a_center, half_len_mm, z0, z1, r_ref):
    half = math.degrees(half_len_mm / r_ref)
    return sector(r_in, r_out, a_center - half, a_center + half, z0, z1, steps=6)


def box(x0, x1, y0, y1, z0, z1):
    x0, x1, y0, y1, z0, z1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), min(z0, z1), max(z0, z1)
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def hook_half_angle():
    return math.degrees(HOOK_LEN / 2 / HOOK_R_OUT)


def dial_hooks():
    solids = []
    for a in HOOK_ANGLES:
        neck = arc_block(HOOK_R_IN, HOOK_R_OUT - NOTCH_DEPTH, a, HOOK_LEN / 2, 0, HOOK_H - LIP_H, HOOK_R_OUT)
        lip = arc_block(HOOK_R_IN, HOOK_R_OUT, a, HOOK_LEN / 2, HOOK_H - LIP_H, HOOK_H, HOOK_R_OUT)
        solids.append(neck.union(lip))
    return solids


def build_ring(bumps=True):
    ring = annulus(SKIRT_R_OUT, SKIRT_R_IN, 0, RING_TOP)
    for a in HOOK_ANGLES:
        ring = ring.union(arc_block(SKIRT_R_IN - TAB_REACH, SKIRT_R_IN + 0.3, a, TAB_LEN / 2, 0, TAB_TOP, SKIRT_R_IN))
        rib_a = a - hook_half_angle() - math.degrees((RIB_W / 2 + CLEAR) / HOOK_R_OUT)
        ring = ring.union(arc_block(HOOK_R_IN + 0.8, SKIRT_R_IN + 0.3, rib_a, RIB_W / 2, 0, HOOK_H - 0.2, HOOK_R_OUT))
    ring = ring.union(annulus(SKIRT_R_IN + 0.3, FLANGE_R_IN, FLANGE_Z0, RING_TOP))
    # spring fingers: free the flange from the skirt along an arc, cut its free end radially
    slot_deg = math.degrees(SLOT / FINGER_R_OUT)
    for a in FINGER_ANGLES:
        a0, a1 = a - FINGER_SPAN / 2, a + FINGER_SPAN / 2
        ring = ring.cut(sector(FINGER_R_OUT, FINGER_R_OUT + SLOT, a0, a1 + slot_deg, FLANGE_Z0 - 0.1, RING_TOP + 0.1))
        ring = ring.cut(sector(FLANGE_R_IN - 0.1, FINGER_R_OUT + SLOT, a1, a1 + slot_deg, FLANGE_Z0 - 0.1, RING_TOP + 0.1, steps=2))
        # rounded bump under the free end, pressing the carrier shoulder
        bx, by = polar(BUMP_R, a1 - 4.0)
        bump = (cq.Workplane("XY").workplane(offset=FLANGE_Z0 - BUMP_DROP).center(bx, by).circle(1.0)
                .extrude(BUMP_DROP + 0.2).edges("<Z").fillet(0.6))
        if bumps:
            ring = ring.union(bump)
    return ring


def build_carrier():
    carrier = annulus(CARRIER_R_LOW, CARRIER_R_IN, 0, LID_Z)
    disc = cq.Workplane("XY").circle(CARRIER_R_IN + 0.5).extrude(LID_Z)
    # PCB pocket: floor rails under the long edges, side walls, end stops
    side = box(PCB_X0 - 1, PCB_X1 + 1, PCB_Y - 1.2, 30, RAIL_Z, PCB_Z)
    side = side.union(box(PCB_X0 - 1, PCB_X1 + 1, PCB_Y + CLEAR, 30, PCB_Z, PCB_Z + PCB_T))
    for s in (side, side.mirror("XZ")):
        carrier = carrier.union(s.intersect(disc))
    end = box(PCB_X1 + CLEAR, 30, -PCB_Y - 1, PCB_Y + 1, RAIL_Z, PCB_Z + PCB_T)
    carrier = carrier.union(end.intersect(disc))
    for y in (1, -1):   # -x end stops beside the cable path
        stop = box(-30, PCB_X0 - CLEAR, y * 5.5, y * 30, RAIL_Z, PCB_Z + PCB_T)
        carrier = carrier.union(stop.intersect(disc))
    # U-shaped screw bosses tied into the wall
    for a in BOSS_ANGLES:
        x, y = polar(BOSS_R, a)
        boss = cq.Workplane("XY").workplane(offset=RAIL_Z).center(x, y).circle(BOSS_D / 2).extrude(LID_Z - RAIL_Z)
        web = (cq.Workplane("XY").workplane(offset=RAIL_Z).rect(3.2, BOSS_D).extrude(LID_Z - RAIL_Z)
               .rotate((0, 0, 0), (0, 0, 1), a).translate((*polar(BOSS_R + 1.6, a), 0)))
        carrier = carrier.union(boss.union(web).intersect(disc))
        carrier = carrier.cut(cq.Workplane("XY").workplane(offset=LID_Z - 6).center(x, y).circle(SCREW_PILOT / 2).extrude(7))
    return carrier


def build_lid():
    lid = cq.Workplane("XY").workplane(offset=LID_Z).circle(LID_R).extrude(LID_T)
    lip = annulus(CARRIER_R_IN - CLEAR, CARRIER_R_IN - CLEAR - 1.0, LID_Z - 1.5, LID_Z)
    for a in BOSS_ANGLES:
        x, y = polar(BOSS_R, a)
        lip = lip.cut(cq.Workplane("XY").workplane(offset=LID_Z - 2).center(x, y).circle(BOSS_D / 2 + 1.0).extrude(2.5))
        lip = lip.cut(cq.Workplane("XY").workplane(offset=LID_Z - 2).rect(3.6, BOSS_D + 2.0).extrude(2.5)
                      .rotate((0, 0, 0), (0, 0, 1), a).translate((*polar(BOSS_R + 1.6, a), 0)))
    lid = lid.union(lip)
    for x, y in POSTS:
        lid = lid.union(cq.Workplane("XY").workplane(offset=PCB_Z + PCB_T + 0.05).center(x, y).circle(1.4)
                        .extrude(LID_Z - (PCB_Z + PCB_T + 0.05)))
    for a in BOSS_ANGLES:
        x, y = polar(BOSS_R, a)
        lid = lid.cut(cq.Workplane("XY").workplane(offset=LID_Z - 1).center(x, y).circle(1.1).extrude(LID_T + 2))
        lid = lid.cut(cq.Workplane("XY").workplane(offset=LID_Z + LID_T - 1.0).center(x, y).circle(2.0).extrude(2))
    lid = lid.cut(cq.Workplane("XY").workplane(offset=LID_Z - 1).center(*CABLE_XY).rect(*CABLE_HOLE).extrude(LID_T + 2))
    top = LID_Z + LID_T
    # LED window: 2.4 mm over the LED, funnelling out to 4.8 mm so it is seen from the side
    # while turning the trimmer, inside a raised ring that marks it and shades it from daylight
    lid = lid.union(cq.Workplane("XY").workplane(offset=top).center(*LED_XY).circle(LED_RING_R).circle(LED_FUNNEL_R)
                    .extrude(LED_RING_H))
    lid = lid.cut(cq.Workplane("XY").workplane(offset=LID_Z - 1).center(*LED_XY).circle(1.2).extrude(LID_T + 2))
    lid = lid.cut(cq.Solid.makeCone(1.2, LED_FUNNEL_R, LID_T + 0.01, cq.Vector(*LED_XY, LID_Z), cq.Vector(0, 0, 1)))
    lid = lid.cut(cq.Workplane("XY").workplane(offset=LID_Z - 1).center(*TRIM_XY).circle(1.9).extrude(LID_T + 2))
    # "SET" engraved beside the trimmer hole
    lid = lid.cut(cq.Workplane("XY").workplane(offset=top - SET_DEPTH).center(*SET_XY)
                  .text("SET", 2.4, SET_DEPTH + 0.1, halign="center", valign="center"))
    # grip bar along the x axis, ending in an arrow at the wheel: turn the carrier by it
    bar = (cq.Workplane("XY").workplane(offset=top)
           .polyline([(-6, -10.5), (14, -10.5), (14, -12.5), (19.5, -8.5), (14, -4.5), (14, -6.5), (-6, -6.5)])
           .close().extrude(2.0))
    lid = lid.union(bar)
    # zip-tie bridge for the cable
    bx = CABLE_XY[0] - CABLE_HOLE[0] / 2 - 2.5
    lid = lid.union(cq.Workplane("XY").workplane(offset=top).center(bx, 0).rect(2.6, 9.0).extrude(3.0)
                    .cut(cq.Workplane("XY").workplane(offset=top).center(bx, 0).rect(2.8, 3.6).extrude(1.8)))
    return lid


def build_test_ring():
    """Quick fit print: the bottom 6 mm of the lock ring (skirt, tabs, stop ribs)."""
    return build_ring().intersect(cq.Workplane("XY").circle(40).extrude(6.0))


def pcb_body():
    slab = box(PCB_X0, PCB_X1, -PCB_Y, PCB_Y, PCB_Z, PCB_Z + PCB_T)
    parts = []
    if COMPONENTS.exists():
        for c in json.loads(COMPONENTS.read_text()):
            b = c["bbox"]
            x0, x1 = b["x0"] - PLAN_OFFSET[0], b["x1"] - PLAN_OFFSET[0]
            y0, y1 = b["y0"] - PLAN_OFFSET[1], b["y1"] - PLAN_OFFSET[1]
            z0, z1 = (PCB_Z - c["height"], PCB_Z) if c["side"] == "back" else (PCB_Z + PCB_T, PCB_Z + PCB_T + c["height"])
            parts.append((c["ref"], box(x0, x1, y0, y1, z0, z1)))
    return slab, parts


def rotated(shape, deg):
    return shape.rotate((0, 0, 0), (0, 0, 1), deg)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    solids = {"dial_reader_ring": build_ring(), "dial_reader_carrier": build_carrier(),
              "dial_reader_lid": build_lid(), "dial_reader_test_ring": build_test_ring()}
    for name, solid in solids.items():
        cq.exporters.export(solid, str(OUT / f"{name}.step"), cq.exporters.ExportTypes.STEP)
        cq.exporters.export(solid, str(OUT / f"{name}.stl"), cq.exporters.ExportTypes.STL, tolerance=0.02, angularTolerance=0.1)
        print(f"dial_reader: exported {name}.step + {name}.stl")
    slab, parts = pcb_body()
    assy = cq.Assembly()
    for name, color in (("dial_reader_ring", (0.15, 0.15, 0.17)), ("dial_reader_carrier", (0.3, 0.3, 0.33)),
                        ("dial_reader_lid", (0.22, 0.22, 0.25))):
        assy.add(solids[name], name=name, color=cq.Color(*color))
    assy.add(slab, name="pcb", color=cq.Color(0.1, 0.4, 0.2))
    for i, hook in enumerate(dial_hooks()):
        assy.add(hook, name=f"dial_hook_{i}", color=cq.Color(0.8, 0.9, 1.0, 0.5))
    assy.save(str(OUT / "dial_reader_assembly.step"))
    render_all(solids, slab, parts)


def render_all(solids, slab, parts):
    import build_distance_pod as bdp

    RENDERS.mkdir(parents=True, exist_ok=True)
    hooks = [(h, (0.75, 0.88, 1.0), 0.6) for h in dial_hooks()]
    glass = cq.Workplane("XY").workplane(offset=-1.0).circle(RING_ID / 2 + 4).extrude(1.0)
    wheel = (cq.Workplane("XY").workplane(offset=-0.9).center(WHEEL_X, 0).circle(WHEEL_D / 2).extrude(0.4)
             .intersect(box(WHEEL_X - 8, WHEEL_X + 8, -8, 0, -1, 0)))
    white = annulus(RING_ID / 2 + 4, RING_ID / 2, -1, 8)
    dial = [(glass, (0.9, 0.93, 0.95), 0.35), (wheel, (0.75, 0.77, 0.8), 1.0), (white, (0.95, 0.95, 0.95), 1.0)]
    board = [(slab, (0.1, 0.45, 0.22), 1.0)] + [(p, (0.1, 0.1, 0.12) if r != "J1" else (0.92, 0.92, 0.92), 1.0) for r, p in parts]
    ring, carrier, lid = solids["dial_reader_ring"], solids["dial_reader_carrier"], solids["dial_reader_lid"]
    rc, cc, lc = (0.16, 0.16, 0.18), (0.32, 0.33, 0.36), (0.24, 0.24, 0.27)
    bdp.render_png(RENDERS / "dial_reader_inside.png", dial + hooks + [(ring, rc, 1.0), (carrier, cc, 1.0)] + board,
                   cam_pos=(-60, -90, 90), focal=(0, 0, 6))
    bdp.render_png(RENDERS / "dial_reader_assembled.png", dial + hooks + [(ring, rc, 1.0), (carrier, cc, 1.0), (lid, lc, 1.0)],
                   cam_pos=(-60, -90, 80), focal=(0, 0, 6))
    bdp.render_png(RENDERS / "dial_reader_bottom.png", hooks + [(ring, rc, 1.0), (carrier, cc, 1.0)] + board,
                   cam_pos=(20, -40, -110), focal=(0, 0, 5), up=(0, 1, 0))
    exploded = dial + hooks + [(carrier.translate((0, 0, 12)), cc, 1.0)] + \
        [(s.translate((0, 0, 22)), c, o) for s, c, o in board] + \
        [(lid.translate((0, 0, 34)), lc, 1.0), (ring.translate((0, 0, 58)), rc, 1.0)]
    bdp.render_png(RENDERS / "dial_reader_exploded.png", exploded, cam_pos=(-90, -130, 80), focal=(0, 0, 28))


if __name__ == "__main__":
    main()
