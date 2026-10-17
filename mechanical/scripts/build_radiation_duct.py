"""CadQuery enclosure & curved in-duct GM tube bracket for the Radiation Counter plugin.

Key mechanical & physical features:
  1. Guaranteed Fit for CAJOE RadiationD-v1.1 (108 x 63 x 20 mm):
     - Rectangular inner cavity is 120.0 x 68.0 x 22.5 mm (2.5 mm clearance around
       the top/bottom/left edges of the 108 x 63 mm PCB, and 8.5 mm clearance on the
       right edge for the overhanging 3-pin output header, 3.5 mm audio jack, and
       DC barrel jack).
     - All 4 lid screw bosses sit in EXTERNAL corner ears outside the 120 x 68 mm
       cavity so zero bosses intrude on the rectangular PCB corners.
     - 4 M3 standoffs at the exact CAJOE hole spacing (102.0 x 57.0 mm) + cover
       hold-down pegs that clamp the PCB corners when the lid is screwed down.
  2. Curved In-Duct GM Tube Bracket (matches ~20 cm / D=200 mm round airduct):
     - The inside-duct mounting flange is shaped with a cylindrical radius matching
       the internal curvature of a ~20 cm (R=100..120 mm) round ventilation duct
       and rounded stadium ends.
     - Suspends the bare J305 glass GM tube (D=10 x 88 mm) 22 mm into the airstream
       with >90% open exposure for Beta & Gamma detection.
     - Routes the +400 V and GND wires straight through two insulated spigots
       (<35 mm wire length, 78 mm apart -> <0.5 pF parasitic capacitance).
  3. Wire Exit Port:
     - D=6.2 mm round cable gland boss on the right wall aligned with the CAJOE
       3-pin pulse output header (+5V, GND, PULSE to 1-DIN Sensor Node).

Outputs under hardware/releases/v1/accessories/radiation_duct/:
  - cajoe_box_base.stl / .step
  - cajoe_box_cover.stl / .step
  - duct_tube_bracket.stl / .step
  - radiation_duct_assembly.step
  - renders/radiation_inside.png (transparent view), radiation_assembled.png,
    radiation_exploded.png
"""

import math
from pathlib import Path

import cadquery as cq
import vtk

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "hardware/releases/v1/accessories/radiation_duct"
RENDERS = OUT / "renders"

# CAJOE RadiationD-v1.1 board & J305 / M4011 GM tube dimensions (mm)
# Official M4011 / J305 specs:
#   - J305 length: 86.5..90.0 mm (M4011: 88.0..90.0 mm), metal end caps 11 mm long at each end
#   - Tube diameter: 10.0 +- 0.5 mm (up to 11.2 mm over heat-shrink / end-cap solder sleeve)
PCB_W = 108.0
PCB_H = 63.0
PCB_T = 1.6
PCB_X_SHIFT = -3.0    # shifted -3 mm left so right side has +8.5 mm for header/jacks
HOLE_DX = 102.0 / 2   # 4 corner M3 holes (102 x 57 mm spacing)
HOLE_DY = 57.0 / 2
# Dual-length tube support matching the 3 clip positions on the CAJOE PCB:
#   - TUBE_X_POS   = -42.0 mm (+ Anode cradle & spigot on the left)
#   - TUBE_X_SHORT = +26.0 mm (- Cathode cradle & spigot for 86.5..90 mm J305 / M4011, 68 mm pitch)
#   - TUBE_X_LONG  = +44.0 mm (- Cathode cradle & spigot for 105..112 mm SBM-20 / STS-5 / long J305, 86 mm pitch)
TUBE_X_POS = -42.0
TUBE_X_SHORT = 26.0
TUBE_X_LONG = 44.0
TUBE_CRADLE_XS = (TUBE_X_POS, TUBE_X_SHORT, TUBE_X_LONG)
TUBE_Y = -16.0        # y offset of the tube axis
TUBE_LEN = 88.0       # nominal M4011 / J305 length shown in reference render
TUBE_DIA = 10.2       # nominal tube OD (cradle bore is 11.6 mm for zero glass stress + heat-shrink clearance)

# Outer box dimensions (mm, z=0 is outer face of airduct wall)
WALL = 2.2
INNER_W = 120.0       # 108 mm PCB + 3.5 mm left + 8.5 mm right (for header & jacks)
INNER_H = 68.0        # 63 mm PCB + 2.5 mm front + 2.5 mm rear
BOX_W = INNER_W + 2 * WALL   # 124.4 mm
BOX_H = INNER_H + 2 * WALL   # 72.4 mm
STANDOFF_H = 5.0
PCB_Z = WALL + STANDOFF_H    # 7.2 mm
BOX_Z = PCB_Z + PCB_T + 22.0 # 30.8 mm (22 mm clearance above PCB for 20 mm tall parts)
LID_T = 2.4

# ~20 cm (D=200 mm, R=100 mm) airduct curvature radius for the in-duct flange
DUCT_RADIUS = 110.0


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def cyl_z(x, y, z0, z1, d):
    return cq.Workplane("XY").circle(d / 2).extrude(z1 - z0).translate((x, y, z0))


def cyl_x(x0, x1, y, z, d):
    return cq.Workplane("YZ", origin=(x0, 0, 0)).center(y, z).circle(d / 2).extrude(x1 - x0)


def build_cajoe_base():
    hw, hh = BOX_W / 2, BOX_H / 2
    shell = box(-hw, hw, -hh, hh, 0, BOX_Z).cut(
        box(-INNER_W / 2, INNER_W / 2, -INNER_H / 2, INNER_H / 2, WALL, BOX_Z + 1)
    )

    # 4 External corner lid screw bosses (outside the 120 x 68 mm inner cavity so
    # the rectangular 108 x 63 mm CAJOE PCB never touches a corner boss!)
    for sx in (-hw - 1.5, hw + 1.5):
        for sy in (-hh + 4.0, hh - 4.0):
            boss = cyl_z(sx, sy, 0, BOX_Z, 7.6).cut(cyl_z(sx, sy, BOX_Z - 12.0, BOX_Z + 1, 2.5))
            shell = shell.union(boss)

    # Side mounting flanges with M4 slots for duct/wall screws
    for s in (-1, 1):
        ear = box(s * hw - (0 if s > 0 else 10.0), s * hw + (10.0 if s > 0 else 0), -16.0, 16.0, 0, 3.4)
        for ey in (-9.0, 9.0):
            ear = ear.cut(cyl_z(s * (hw + 5.0), ey, -1, 5, 4.2))
        shell = shell.union(ear)

    # 4 PCB corner standoffs at exact CAJOE hole spacing (102 x 57 mm, M3 pilot 2.5 mm)
    for dx in (-HOLE_DX, HOLE_DX):
        for dy in (-HOLE_DY, HOLE_DY):
            sx = PCB_X_SHIFT + dx
            post = cyl_z(sx, dy, WALL, PCB_Z, 6.8).cut(cyl_z(sx, dy, WALL + 1.0, PCB_Z + 1, 2.5))
            shell = shell.union(post)

    # Three insulated HV wire feedthrough spigots matching the 3 CAJOE tube pads:
    #   x = -42.0 mm (+ Anode), x = +26.0 mm (- Short tube), x = +44.0 mm (- Long tube)
    # Plus two M4 through-duct clamping bosses at x = -52.0 and +52.0 mm
    for sx in TUBE_CRADLE_XS:
        spigot = cyl_z(sx, TUBE_Y, -4.5, WALL + 2.5, 9.6)
        shell = shell.union(spigot).cut(cyl_z(sx, TUBE_Y, -5.5, WALL + 4.0, 5.0))
    for sx in (-52.0, 52.0):
        clamp = cyl_z(sx, TUBE_Y, 0, WALL + 4.0, 8.5).cut(cyl_z(sx, TUBE_Y, -1, WALL + 5.0, 3.4))
        shell = shell.union(clamp)

    # Round D=6.2 mm cable gland boss on right wall (+x) for the 3-wire low-voltage
    # cable (+5V, GND, PULSE to 1-DIN Sensor Node)
    cable_y, cable_z = -8.0, PCB_Z + 7.0
    gland = cyl_x(hw - WALL - 1.0, hw + 2.5, cable_y, cable_z, 10.5)
    shell = shell.union(gland).cut(cyl_x(hw - WALL - 2.0, hw + 4.0, cable_y, cable_z, 6.2))
    return shell


def build_cajoe_cover():
    hw, hh = BOX_W / 2, BOX_H / 2
    lid = box(-hw, hw, -hh, hh, BOX_Z, BOX_Z + LID_T)
    # External corner ears matching the base's external screw bosses
    for sx in (-hw - 1.5, hw + 1.5):
        for sy in (-hh + 4.0, hh - 4.0):
            lid = lid.union(cyl_z(sx, sy, BOX_Z, BOX_Z + LID_T, 7.6))
            lid = lid.cut(cyl_z(sx, sy, BOX_Z - 1.0, BOX_Z + LID_T + 1.0, 3.2))

    # Inner locating lip
    lip = box(-INNER_W / 2 + 0.25, INNER_W / 2 - 0.25, -INNER_H / 2 + 0.25, INNER_H / 2 - 0.25, BOX_Z - 1.6, BOX_Z).cut(
        box(-INNER_W / 2 + 1.6, INNER_W / 2 - 1.6, -INNER_H / 2 + 1.6, INNER_H / 2 - 1.6, BOX_Z - 2.0, BOX_Z + 1)
    )
    lid = lid.union(lip)

    # 4 Hold-down pegs from the cover down onto the 4 corners of the CAJOE PCB
    # (so the CAJOE board is clamped onto its standoffs even without M3 screws!)
    pcb_top = PCB_Z + PCB_T
    for dx in (-HOLE_DX, HOLE_DX):
        for dy in (-HOLE_DY, HOLE_DY):
            sx = PCB_X_SHIFT + dx
            peg = cyl_z(sx, dy, pcb_top + 0.2, BOX_Z + 0.1, 5.2)
            pin = cyl_z(sx, dy, PCB_Z + 0.2, pcb_top + 0.3, 2.4)
            lid = lid.union(peg).union(pin)

    # Viewing window over the CAJOE pulse LED (x = PCB_X_SHIFT + 38, y = 22)
    lid = lid.cut(cyl_z(PCB_X_SHIFT + 38.0, 22.0, BOX_Z - 3.0, BOX_Z + LID_T + 1, 4.5))
    return lid


def build_duct_tube_bracket():
    """Open-frame bracket inside the airduct (z < 0, tube centre at z = -23 mm).
    Supports BOTH tube lengths used on the CAJOE RadiationD-v1.1 board:
      1. Short tubes (86.5..90 mm J305 / M4011): supported at x = -42.0 mm (+) and
         x = +26.0 mm (- inner cradle, 68 mm pitch).
      2. Long tubes (105..112 mm SBM-20 / STS-5 / long J305): supported at x = -42.0 mm (+)
         and x = +44.0 mm (- outer cradle, 86 mm pitch).
    All three coaxial cradles have a D = 11.6 mm axial slide-in bore, 9.8 mm throat,
    zip-tie/O-ring retention slots, and D = 5.0 mm HV wire channels."""
    tz = -23.0
    r_outer = 8.0
    r_tube = 11.6 / 2  # 5.8 mm (D = 11.6 mm bore: clears D10+-0.5mm tube + heat-shrink sleeve)

    flange_blank = (
        cq.Workplane("XY")
        .center(0, TUBE_Y)
        .slot2D(118.0, 22.0, 0)
        .extrude(7.5)
        .translate((0, 0, -7.5))
    )
    r_arc = 185.0
    top_cutter = cq.Workplane("YZ", origin=(-62, 0, 0)).center(TUBE_Y, -r_arc).circle(r_arc).extrude(124)
    inner_cutter = cq.Workplane("YZ", origin=(-62, 0, 0)).center(TUBE_Y, -r_arc).circle(r_arc - 3.6).extrude(124)
    flange = flange_blank.intersect(top_cutter).cut(inner_cutter)

    # Three coaxial support pillars + open-ended cradles at x = -42.0 (+), +26.0 (- short), +44.0 (- long)
    for sx in TUBE_CRADLE_XS:
        z_flange_at_x = -(r_arc - math.sqrt(r_arc ** 2 - sx ** 2))
        pillar = box(sx - 4.5, sx + 4.5, TUBE_Y - 6.0, TUBE_Y + 6.0, tz, z_flange_at_x - 1.0)
        cradle = cyl_x(sx - 4.5, sx + 4.5, TUBE_Y, tz, r_outer * 2)
        flange = flange.union(pillar).union(cradle)

    # Two aerodynamic side guard bows spanning from x = -42.0 to x = +44.0 (leave both
    # axial ends completely open so tubes from 75 mm to 112 mm slide in freely)
    for dy in (-9.6, 9.6):
        bow = box(TUBE_X_POS, TUBE_X_LONG, TUBE_Y + dy - 1.2, TUBE_Y + dy + 1.2, tz - 2.0, tz + 2.0)
        for sx in TUBE_CRADLE_XS:
            strut = box(sx - 2.0, sx + 2.0, min(TUBE_Y, TUBE_Y + dy), max(TUBE_Y, TUBE_Y + dy), tz - 2.0, tz + 2.0)
            flange = flange.union(strut)
        flange = flange.union(bow)

    # Cut the D=11.6 mm coaxial tube bore + 9.8 mm bottom throat + zip-tie slots + D=5.0 mm HV wire channels
    flange = flange.cut(cyl_x(TUBE_X_POS - 8.0, TUBE_X_LONG + 8.0, TUBE_Y, tz, r_tube * 2))
    flange = flange.cut(box(TUBE_X_POS - 8.0, TUBE_X_LONG + 8.0, TUBE_Y - 4.9, TUBE_Y + 4.9, tz - r_outer - 1, tz))
    for sx in TUBE_CRADLE_XS:
        # Zip-tie / O-ring retention slot through each pillar at z = tz + 7.5 mm
        flange = flange.cut(box(sx - 1.8, sx + 1.8, TUBE_Y - 7.0, TUBE_Y + 7.0, tz + 6.5, tz + 9.5))
        # D=5.0 mm HV wire channel + D=10.0 mm spigot socket
        flange = flange.cut(cyl_z(sx, TUBE_Y, tz, 2.0, 5.0))
        flange = flange.cut(cyl_z(sx, TUBE_Y, -5.0, 2.0, 10.0))

    # Through-duct M3/M4 bolt holes at x = -52.0 and +52.0 mm
    for sx in (-52.0, 52.0):
        flange = flange.cut(cyl_z(sx, TUBE_Y, -8.0, 2.0, 3.6))

    return flange


def cajoe_board_and_tube_solids():
    """Reference 3D solids for the 108x63x20 mm CAJOE PCB + components, J305 GM
    tube, HV wires, and 3-wire output cable."""
    x0, x1 = PCB_X_SHIFT - PCB_W / 2, PCB_X_SHIFT + PCB_W / 2
    pcb = box(x0, x1, -PCB_H / 2, PCB_H / 2, PCB_Z, PCB_Z + PCB_T)
    for dx in (-HOLE_DX, HOLE_DX):
        for dy in (-HOLE_DY, HOLE_DY):
            pcb = pcb.cut(cyl_z(PCB_X_SHIFT + dx, dy, PCB_Z - 1, PCB_Z + PCB_T + 1, 3.2))
    top_z = PCB_Z + PCB_T
    buzzer = cyl_z(PCB_X_SHIFT + 12.0, 20.0, top_z, top_z + 9.5, 12.0)
    led = cyl_z(PCB_X_SHIFT + 38.0, 22.0, top_z, top_z + 5.0, 3.0)
    hv_ind = cyl_z(PCB_X_SHIFT - 28.0, 12.0, top_z, top_z + 14.0, 9.5)
    hv_cap = box(PCB_X_SHIFT - 42.0, PCB_X_SHIFT - 32.0, -4.0, 8.0, top_z, top_z + 18.0)
    pot = box(PCB_X_SHIFT - 14.0, PCB_X_SHIFT - 4.0, -4.0, 6.0, top_z, top_z + 10.0)
    ic1 = box(PCB_X_SHIFT + 8.0, PCB_X_SHIFT + 18.0, -8.0, 4.0, top_z, top_z + 4.5)
    hdr = box(x1 - 3.5, x1 + 4.5, -12.0, -4.0, top_z, top_z + 8.5)
    out_cable = cyl_x(x1 + 2.0, BOX_W / 2 + 16.0, -8.0, PCB_Z + 7.0, 4.5)

    # J305 / M4011 glass tube inside the duct (z = -23.0, seated in the -42.0 and +26.0
    # short-tube cradles, while the +44.0 long-tube cradle is visible to its right)
    tz = -23.0
    x_tube_l, x_tube_r = TUBE_X_POS - 5.5, TUBE_X_SHORT + 5.5
    glass = cyl_x(x_tube_l + 11.0, x_tube_r - 11.0, TUBE_Y, tz, TUBE_DIA)
    cap_l = cyl_x(x_tube_l, x_tube_l + 11.0, TUBE_Y, tz, TUBE_DIA + 0.3)
    cap_r = cyl_x(x_tube_r - 11.0, x_tube_r, TUBE_Y, tz, TUBE_DIA + 0.3)
    wire_pos = cyl_z(TUBE_X_POS, TUBE_Y, tz, top_z + 2.0, 1.8)
    wire_neg = cyl_z(TUBE_X_SHORT, TUBE_Y, tz, top_z + 2.0, 1.8)
    return [
        (pcb, (0.08, 0.35, 0.62)),
        (buzzer, (0.14, 0.14, 0.16)),
        (led, (0.90, 0.15, 0.15)),
        (hv_ind, (0.20, 0.22, 0.25)),
        (hv_cap, (0.15, 0.42, 0.78)),
        (pot, (0.18, 0.48, 0.82)),
        (ic1, (0.16, 0.16, 0.18)),
        (hdr, (0.18, 0.18, 0.20)),
        (out_cable, (0.20, 0.20, 0.22)),
        (wire_pos, (0.88, 0.18, 0.18)),
        (wire_neg, (0.18, 0.18, 0.20)),
        (glass, (0.78, 0.58, 0.38)),
        (cap_l, (0.78, 0.80, 0.82)),
        (cap_r, (0.78, 0.80, 0.82)),
    ]


def actor(shape, rgb, opacity=1.0, edges=False):
    vertices, faces = shape.val().tessellate(0.15, 0.2)
    points = vtk.vtkPoints()
    for v in vertices:
        points.InsertNextPoint(v.x, v.y, v.z)
    polys = vtk.vtkCellArray()
    for f in faces:
        polys.InsertNextCell(3, f)
    data = vtk.vtkPolyData()
    data.SetPoints(points)
    data.SetPolys(polys)
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(data)
    normals.SetFeatureAngle(35)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(normals.GetOutputPort())
    a = vtk.vtkActor()
    a.SetMapper(mapper)
    a.GetProperty().SetColor(*rgb)
    a.GetProperty().SetOpacity(opacity)
    a.GetProperty().SetSpecular(0.15)
    if edges:
        a.GetProperty().SetEdgeVisibility(1)
        a.GetProperty().SetEdgeColor(0.25, 0.30, 0.38)
        a.GetProperty().SetLineWidth(1.0)
    return a


def render_png(path, items, cam_pos, focal=(0, 0, 0), up=(0, 0, 1), zoom=1.0):
    renderer = vtk.vtkRenderer()
    renderer.SetBackground(1, 1, 1)
    renderer.SetUseDepthPeeling(1)
    renderer.SetMaximumNumberOfPeels(30)
    for item in items:
        shape, rgb, op = item[:3]
        edges = item[3] if len(item) > 3 else False
        renderer.AddActor(actor(shape, rgb, op, edges=edges))
    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.SetAlphaBitPlanes(1)
    win.SetMultiSamples(0)
    win.SetSize(1400, 1100)
    win.AddRenderer(renderer)
    cam = renderer.GetActiveCamera()
    cam.SetPosition(*cam_pos)
    cam.SetFocalPoint(*focal)
    cam.SetViewUp(*up)
    renderer.ResetCamera()
    cam.Zoom(zoom)
    win.Render()
    grab = vtk.vtkWindowToImageFilter()
    grab.SetInput(win)
    grab.Update()
    w = vtk.vtkPNGWriter()
    w.SetFileName(str(path))
    w.SetInputConnection(grab.GetOutputPort())
    w.Write()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RENDERS.mkdir(parents=True, exist_ok=True)

    base = build_cajoe_base()
    cover = build_cajoe_cover()
    bracket = build_duct_tube_bracket()

    for name, solid in (("cajoe_box_base", base), ("cajoe_box_cover", cover), ("duct_tube_bracket", bracket)):
        cq.exporters.export(solid, str(OUT / f"{name}.step"), cq.exporters.ExportTypes.STEP)
        cq.exporters.export(solid, str(OUT / f"{name}.stl"), cq.exporters.ExportTypes.STL)
        print(f"radiation_duct: exported {name}.step + {name}.stl")

    assy = base.union(cover).union(bracket)
    for s, _ in cajoe_board_and_tube_solids():
        assy = assy.union(s)
    cq.exporters.export(assy, str(OUT / "radiation_duct_assembly.step"), cq.exporters.ExportTypes.STEP)

    CASE = (0.84, 0.85, 0.88)
    LID_COL = (0.76, 0.78, 0.82)
    XRAY_BASE = (0.45, 0.58, 0.75)
    XRAY_LID = (0.35, 0.48, 0.68)
    BRACKET = (0.22, 0.25, 0.30)
    board_parts = cajoe_board_and_tube_solids()
    ref_parts = [(s, rgb, 1.0) for s, rgb in board_parts]

    # 1. Transparent X-Ray Inside View (shows CAJOE clearance, corner hold-down pegs,
    #    right-wall cable gland, HV spigots, and curved in-duct GM tube bracket)
    render_png(RENDERS / "radiation_inside.png",
               [(base, XRAY_BASE, 0.22, True), (cover, XRAY_LID, 0.22, True), (bracket, BRACKET, 0.88, True)] + ref_parts,
               (175, -205, 95), focal=(0, -4, 0), zoom=1.15)

    # 2. Cutaway Assembled View
    cover_cut = cover.intersect(box(-100, 100, -2.0, 100, -50, 60))
    render_png(RENDERS / "radiation_assembled.png",
               [(base, CASE, 1.0), (cover_cut, LID_COL, 1.0), (bracket, BRACKET, 1.0)] + ref_parts,
               (175, -205, 95), focal=(0, -4, 0), zoom=1.15)

    # 3. Exploded View
    pcb_layer = [(s.translate((0, 0, 20)), rgb, 1.0) for s, rgb in board_parts[:9]]
    tube_layer = [(s.translate((0, 0, -28)), rgb, 1.0) for s, rgb in board_parts[9:]]
    exploded = [
        (bracket.translate((0, 0, -28)), BRACKET, 1.0),
        *tube_layer,
        (base, CASE, 1.0),
        *pcb_layer,
        (cover.translate((0, 0, 48)), LID_COL, 0.78, True),
    ]
    render_png(RENDERS / "radiation_exploded.png", exploded,
               (200, -235, 115), focal=(0, -4, 8), zoom=1.1)
    print(f"radiation_duct renders saved to {RENDERS.relative_to(REPO)}")


if __name__ == "__main__":
    main()
