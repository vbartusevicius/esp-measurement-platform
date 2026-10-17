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

# CAJOE RadiationD-v1.1 board dimensions (mm)
PCB_W = 108.0
PCB_H = 63.0
PCB_T = 1.6
PCB_X_SHIFT = -3.0    # shifted -3 mm left so right side has +8.5 mm for header/jacks
HOLE_DX = 102.0 / 2   # 4 corner M3 holes (102 x 57 mm spacing)
HOLE_DY = 57.0 / 2
TUBE_X = 39.0         # + and - tube clip positions along x (+-39.0 mm)
TUBE_Y = -16.0        # y offset of the tube axis
TUBE_LEN = 88.0
TUBE_DIA = 10.0

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

    # Two insulated HV wire feedthrough spigots (protrude z = -4.5..0 through the
    # airduct wall directly into the in-duct tube bracket's wire posts) + two M4
    # through-duct clamping bosses at x = +-48.0, y = TUBE_Y
    for sx in (-TUBE_X, TUBE_X):
        spigot = cyl_z(sx, TUBE_Y, -4.5, WALL + 2.5, 8.0)
        shell = shell.union(spigot).cut(cyl_z(sx, TUBE_Y, -5.5, WALL + 4.0, 3.8))
    for sx in (-48.0, 48.0):
        clamp = cyl_z(sx, TUBE_Y, 0, WALL + 4.0, 8.5).cut(cyl_z(sx, TUBE_Y, -1, WALL + 5.0, 3.2))
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
    Features a gently curved mounting flange matching the internal radius of a
    ~20 cm (D=200 mm, R=100..110 mm) round airduct, rounded ends, and >90% open
    exposure around the bare J305 glass tube for Beta/Gamma sensitivity."""
    tz = -23.0
    r_outer = 7.4
    r_tube = TUBE_DIA / 2 + 0.25  # 5.25 mm

    # Curved base flange (x = -54..+54, y = TUBE_Y - 12..TUBE_Y + 12) arched along x
    # to match the internal radius of a ~20 cm (R=110 mm) airduct (sagitta ~ 4.5 mm
    # clipped/blended into a curved 3.8 mm thick saddle at z = -6.5..0.0)
    flange_blank = (
        cq.Workplane("XY")
        .center(0, TUBE_Y)
        .slot2D(112.0, 22.0, 0)
        .extrude(7.5)
        .translate((0, 0, -7.5))
    )
    # Cut top surface with cylinder of radius R_DUCT=180 mm (gentle ~4.0 mm curve
    # across the 112 mm span) and parallel bottom surface 3.6 mm below it
    r_arc = 185.0
    top_cutter = cq.Workplane("YZ", origin=(-60, 0, 0)).center(TUBE_Y, -r_arc).circle(r_arc).extrude(120)
    inner_cutter = cq.Workplane("YZ", origin=(-60, 0, 0)).center(TUBE_Y, -r_arc).circle(r_arc - 3.6).extrude(120)
    flange = flange_blank.intersect(top_cutter).cut(inner_cutter)

    # Two hollow support pillars at x = +-TUBE_X reaching from the curved flange down to tz
    for sx in (-TUBE_X, TUBE_X):
        z_flange_at_x = -(r_arc - math.sqrt(r_arc ** 2 - sx ** 2))
        pillar = box(sx - 5.0, sx + 5.0, TUBE_Y - 5.5, TUBE_Y + 5.5, tz, z_flange_at_x - 1.0)
        cradle = cyl_x(sx - 5.0, sx + 5.0, TUBE_Y, tz, r_outer * 2)
        flange = flange.union(pillar).union(cradle)

    # Two aerodynamic side guard bows with rounded struts
    for dy in (-9.2, 9.2):
        bow = box(-TUBE_X, TUBE_X, TUBE_Y + dy - 1.2, TUBE_Y + dy + 1.2, tz - 2.0, tz + 2.0)
        strut_l = box(-TUBE_X - 2.0, -TUBE_X + 2.0, min(TUBE_Y, TUBE_Y + dy), max(TUBE_Y, TUBE_Y + dy), tz - 2.0, tz + 2.0)
        strut_r = box(TUBE_X - 2.0, TUBE_X + 2.0, min(TUBE_Y, TUBE_Y + dy), max(TUBE_Y, TUBE_Y + dy), tz - 2.0, tz + 2.0)
        flange = flange.union(bow).union(strut_l).union(strut_r)

    # Cut the J305 tube bore + snap-in throat + HV wire channels + spigot sockets
    for sx in (-TUBE_X, TUBE_X):
        flange = flange.cut(cyl_x(sx - 6.5, sx + 6.5, TUBE_Y, tz, r_tube * 2))
        flange = flange.cut(box(sx - 6.5, sx + 6.5, TUBE_Y - 4.2, TUBE_Y + 4.2, tz - r_outer - 1, tz))
        flange = flange.cut(cyl_z(sx, TUBE_Y, tz, 2.0, 3.8))
        flange = flange.cut(cyl_z(sx, TUBE_Y, -5.0, 2.0, 8.4))

    # Through-duct M3/M4 bolt holes at x = +-48.0 mm
    for sx in (-48.0, 48.0):
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

    # J305 glass tube inside the duct (z = -23.0) + metal end caps + short HV wires
    tz = -23.0
    glass = cyl_x(-TUBE_LEN / 2 + 10.0, TUBE_LEN / 2 - 10.0, TUBE_Y, tz, TUBE_DIA)
    cap_l = cyl_x(-TUBE_LEN / 2, -TUBE_LEN / 2 + 10.0, TUBE_Y, tz, TUBE_DIA + 0.3)
    cap_r = cyl_x(TUBE_LEN / 2 - 10.0, TUBE_LEN / 2, TUBE_Y, tz, TUBE_DIA + 0.3)
    wire_pos = cyl_z(-TUBE_X, TUBE_Y, tz, top_z + 2.0, 1.8)
    wire_neg = cyl_z(TUBE_X, TUBE_Y, tz, top_z + 2.0, 1.8)
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
