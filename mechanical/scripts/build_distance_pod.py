"""CadQuery Universal Distance Sensor Pod — verified against manufacturer
dimension drawings for BOTH:
  1. DFRobot A02YYUW (SEN0311) IP67 Dual-Transducer Ultrasonic Sensor:
     - Total width across mounting ears: 84.6 +- 0.5 mm
     - Mounting ear hole pitch: 72.6 +- 0.4 mm (x = +-36.3 mm), D = 3.2 +- 0.1 mm (M3)
     - Mounting ear thickness: 4.0 +- 0.2 mm (flush with top/back of 12.5 mm body)
     - Main body: 63.6 x 29.6 x 12.5 mm (rounded ends)
     - Two stepped transducer horns at 34.0 +- 0.3 mm pitch (x = +-17.0 mm):
         * Base collar: D = 18.0 +- 0.2 mm, height = 4.0 +- 0.2 mm
         * Front tip:   D = 12.5 +- 0.1 mm, height = 2.0 +- 0.1 mm (total 6.0 mm horn)
     - Captive cable strain-relief boot (14 mm long) at rear centre (x = 0, y = +14.8 mm)
  2. TOF400C-VL53L1X / TOF200C (20.0 x 11.5 mm PCB with built-in 12.0 x 7.5 x 3.2 mm
     oval anti-crosstalk optical cover cap, M2 holes at 15.4 mm pitch / x = +-7.7 mm)
     AND GY-530 / bare VL53L1X (25.0 x 10.7 mm PCB, M2.5 holes at 19.6 mm pitch /
     x = +-9.8 mm, with 18.4 x 18.4 x 0.7 mm recess for an 18x18 mm #1.5 cover slip).

Outputs under hardware/releases/v1/accessories/distance_sensor_pod/:
  - distance_pod_base.stl / .step
  - distance_pod_cover.stl / .step
  - distance_pod_assembly.step
  - renders/distance_pod_inside.png, distance_pod_assembled.png, distance_pod_exploded.png
"""

from pathlib import Path

import cadquery as cq
import vtk

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "hardware/releases/v1/accessories/distance_sensor_pod"
RENDERS = OUT / "renders"

WALL = 2.2
INNER_W = 87.0                # 84.6 mm A02YYUW ear span + 2.4 mm clearance
INNER_H = 64.0                # Bay 1 (ToF at y=-21) + Bay 2 (A02YYUW at y=+3 + 14mm boot)
POD_W = INNER_W + 2 * WALL    # 91.4 mm
POD_H = INNER_H + 2 * WALL    # 68.4 mm
POD_Z = 21.5                  # 18.5 mm A02YYUW total height + 3.0 mm top clamp/clearance
LID_T = 2.4

# --- Bay 1 (Front, y = -21.0 mm): TOF400C-VL53L1X & GY-530 Laser Sensor ---
TOF_Y = -21.0
TOF_HOLE_DX_400C = 7.7        # TOF400C / TOF200C M2 hole pitch = 15.4 mm
TOF_HOLE_DX_GY530 = 9.8       # GY-530 VL53L1X hole pitch = 19.6 mm
TOF_STANDOFF_Z = 3.4          # matches 3.2 mm tall built-in oval lens cap on TOF400C
TOF_PCB_T = 1.6               # top of ToF PCB at z = 5.0 mm

# --- Bay 2 (Rear, y = +3.0 mm): DFRobot A02YYUW (SEN0311) Ultrasonic ---
US_Y = 3.0
US_BODY_W = 63.6
US_BODY_D = 29.6
US_BODY_H = 12.5
US_EAR_SPAN = 84.6
US_EAR_HOLE_DX = 72.6 / 2     # 36.3 mm (exact SEN0311 drawing: 72.6 +- 0.4 mm)
US_EAR_T = 4.0                # 4.0 +- 0.2 mm ear thickness at top of body
US_HORN_DX = 34.0 / 2         # 17.0 mm (exact SEN0311 drawing: 34.0 +- 0.3 mm)
US_HORN_TIP_D = 12.5          # D=12.5 +- 0.1 mm front tip (2.0 mm tall, z = 0..2.0)
US_HORN_BASE_D = 18.0         # D=18.0 +- 0.2 mm base step (4.0 mm tall, z = 2.0..6.0)
US_SEAT_Z = 6.0               # 2.0 mm tip + 4.0 mm base collar -> body sits at z = 6.0..18.5 mm
US_TOP_Z = US_SEAT_Z + US_BODY_H  # 18.5 mm


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def cyl_z(x, y, z0, z1, d):
    return cq.Workplane("XY").circle(d / 2).extrude(z1 - z0).translate((x, y, z0))


def cyl_x(x0, x1, y, z, d):
    return cq.Workplane("YZ", origin=(x0, 0, 0)).center(y, z).circle(d / 2).extrude(x1 - x0)


def cyl_y(x, y0, y1, z, d):
    return cq.Workplane("XZ", origin=(0, y0, 0)).center(x, z).circle(d / 2).extrude(-(y1 - y0))


def build_pod_base():
    hw, hh = POD_W / 2, POD_H / 2
    shell = box(-hw, hw, -hh, hh, 0, POD_Z).cut(
        box(-INNER_W / 2, INNER_W / 2, -INNER_H / 2, INNER_H / 2, WALL, POD_Z + 1)
    )

    # 4 External corner lid screw bosses (outside the inner cavity so the 84.6 mm
    # A02YYUW ears have full width inside the box)
    for sx in (-hw - 1.2, hw + 1.2):
        for sy in (-hh + 4.0, hh - 4.0):
            boss = cyl_z(sx, sy, 0, POD_Z, 7.2).cut(cyl_z(sx, sy, POD_Z - 12.0, POD_Z + 1, 2.5))
            shell = shell.union(boss)

    # Side mounting flanges (screw onto the underside of the tank lid)
    for s in (-1, 1):
        ear = box(s * hw - (0 if s > 0 else 9.0), s * hw + (9.0 if s > 0 else 0), -14.0, 14.0, POD_Z - 3.4, POD_Z)
        for ey in (-8.0, 8.0):
            ear = ear.cut(cyl_z(s * (hw + 4.5), ey, POD_Z - 4.0, POD_Z + 1.0, 4.2))
        shell = shell.union(ear)

    # --- Bay 1 (y = TOF_Y = -21.0): TOF400C-VL53L1X & GY-530 Laser Sensor ---
    # 1. Stadium aperture (12.8 x 8.2 mm) through floor for TOF400C's built-in
    #    12.0 x 7.5 x 3.2 mm oval anti-crosstalk optical cover cap
    tof_slot = cq.Workplane("XY").center(0, TOF_Y).slot2D(12.8, 8.2, 0).extrude(TOF_STANDOFF_Z + 1.0).translate((0, 0, -0.5))
    # 2. Outer 18.4 x 18.4 x 0.7 mm bottom pocket for an optional 18x18 mm #1.5 cover slip
    glass_pocket = box(-9.2, 9.2, TOF_Y - 9.2, TOF_Y + 9.2, -0.1, 0.7)
    # 3. Dual-pitch support pads covering BOTH TOF400C (x = +-7.7 mm) and GY-530 (x = +-9.8 mm)
    for s in (-1, 1):
        pad = box(s * 6.4 if s > 0 else -12.6, 12.6 if s > 0 else -6.4, TOF_Y - 3.5, TOF_Y + 3.5, WALL, TOF_STANDOFF_Z)
        shell = shell.union(pad)
    shell = shell.cut(tof_slot).cut(glass_pocket)
    for dx in (TOF_HOLE_DX_400C, TOF_HOLE_DX_GY530):
        for s in (-1, 1):
            shell = shell.cut(cyl_z(s * dx, TOF_Y, 0.8, TOF_STANDOFF_Z + 0.5, 1.8))

    # --- Bay 2 (y = US_Y = +3.0): DFRobot A02YYUW (SEN0311) Sealed Ultrasonic ---
    # 1. Stepped transducer horn collars at x = +-17.0 mm (34.0 mm pitch):
    #    - Bottom tip bore (z = 0..2.0 mm): D = 13.3 mm (for D = 12.5 mm horn tip)
    #    - Upper base counterbore (z = 2.0..6.0 mm): D = 18.8 mm (for D = 18.0 mm horn base)
    for sx in (-US_HORN_DX, US_HORN_DX):
        collar = cyl_z(sx, US_Y, WALL, US_SEAT_Z, US_HORN_BASE_D + 4.4)
        shell = shell.union(collar)
        shell = shell.cut(cyl_z(sx, US_Y, -1.0, 2.1, US_HORN_TIP_D + 0.8))
        shell = shell.cut(cyl_z(sx, US_Y, 2.0, US_SEAT_Z + 1.0, US_HORN_BASE_D + 0.8))

    # 2. Mounting ear support pillars at x = +-36.3 mm (72.6 mm pitch), rising to
    #    z = US_TOP_Z - US_EAR_T = 14.5 mm with M3 pilot holes (D = 2.6 mm)
    ear_seat_z = US_TOP_Z - US_EAR_T  # 14.5 mm
    for sx in (-US_EAR_HOLE_DX, US_EAR_HOLE_DX):
        post = cyl_z(sx, US_Y, WALL, ear_seat_z, 7.6).cut(cyl_z(sx, US_Y, WALL + 2.0, ear_seat_z + 1.0, 2.6))
        shell = shell.union(post)

    # --- Rear Cable Gland Port (D = 6.5 mm at x = +16.0, y = +hh) + Strain-Relief Saddle ---
    # Placed behind the sensors so the A02YYUW captive cable boot (at x=0, y=US_Y+14.8..+28.8)
    # bends gently into the strain-relief saddle and exits without pinching.
    cable_x, cable_z = 16.0, 13.5
    gland = cyl_y(cable_x, hh - WALL - 1.0, hh + 2.5, cable_z, 10.8)
    shell = shell.union(gland).cut(cyl_y(cable_x, hh - WALL - 2.0, hh + 4.0, cable_z, 6.5))
    saddle = box(cable_x - 4.5, cable_x + 4.5, hh - 9.0, hh - 4.0, WALL, cable_z - 3.2)
    saddle = saddle.cut(box(cable_x - 5.0, cable_x + 5.0, hh - 8.0, hh - 5.0, WALL + 1.5, cable_z - 4.6))
    shell = shell.union(saddle)

    return shell


def build_pod_cover():
    """Cover with integrated hold-down compression pillars & ribs that lock BOTH
    the TOF400C/VL53L1X PCB (at z = 5.0 mm) and the A02YYUW body + ears (at z = 18.5 mm)."""
    hw, hh = POD_W / 2, POD_H / 2
    lid = box(-hw, hw, -hh, hh, POD_Z, POD_Z + LID_T)
    for sx in (-hw - 1.2, hw + 1.2):
        for sy in (-hh + 4.0, hh - 4.0):
            lid = lid.union(cyl_z(sx, sy, POD_Z, POD_Z + LID_T, 7.2))
            lid = lid.cut(cyl_z(sx, sy, POD_Z - 1.0, POD_Z + LID_T + 1.0, 3.2))

    lip = box(-INNER_W / 2 + 0.25, INNER_W / 2 - 0.25, -INNER_H / 2 + 0.25, INNER_H / 2 - 0.25, POD_Z - 1.6, POD_Z).cut(
        box(-INNER_W / 2 + 1.6, INNER_W / 2 - 1.6, -INNER_H / 2 + 1.6, INNER_H / 2 - 1.6, POD_Z - 2.0, POD_Z + 1)
    )
    lid = lid.union(lip)

    # 1. Hold-down compression blocks for TOF400C / GY-530 PCB (press down to z = 5.1 mm)
    tof_top = TOF_STANDOFF_Z + TOF_PCB_T  # 5.0 mm
    for s in (-1, 1):
        clamp = box(s * 6.5 if s > 0 else -11.5, 11.5 if s > 0 else -6.5,
                    TOF_Y - 2.8, TOF_Y + 2.8, tof_top + 0.1, POD_Z + 0.1)
        lid = lid.union(clamp)

    # 2. Hold-down compression ribs + M3 ear bosses for A02YYUW (press down to z = 18.6 mm)
    for sx in (-US_HORN_DX, US_HORN_DX):
        rib = box(sx - 4.5, sx + 4.5, US_Y - 10.0, US_Y + 10.0, US_TOP_Z + 0.1, POD_Z + 0.1)
        lid = lid.union(rib)
    for sx in (-US_EAR_HOLE_DX, US_EAR_HOLE_DX):
        ear_clamp = cyl_z(sx, US_Y, US_TOP_Z + 0.1, POD_Z + 0.1, 7.2)
        ear_pin = cyl_z(sx, US_Y, US_TOP_Z - US_EAR_T + 0.2, US_TOP_Z + 0.2, 2.8)
        lid = lid.union(ear_clamp).union(ear_pin)

    return lid


def sensor_reference_solids():
    """Exact datasheet reference 3D solids for:
      1. TOF400C-VL53L1X (20.0 x 11.5 x 1.6 mm PCB + 12.0 x 7.5 x 3.2 mm oval optical cap,
         M2 holes at +-7.7 mm)
      2. DFRobot A02YYUW / SEN0311 (63.6 x 29.6 x 12.5 mm body, 84.6 mm ears at top with
         D=3.2 mm holes at +-36.3 mm, stepped D=18.0/12.5 mm horns at +-17.0 mm, and
         rear captive cable boot)."""
    # 1. TOF400C-VL53L1X module + built-in oval optical cover cap
    tof_pcb = box(-10.0, 10.0, TOF_Y - 5.75, TOF_Y + 5.75, TOF_STANDOFF_Z, TOF_STANDOFF_Z + TOF_PCB_T)
    for sx in (-TOF_HOLE_DX_400C, TOF_HOLE_DX_400C):
        tof_pcb = tof_pcb.cut(cyl_z(sx, TOF_Y, TOF_STANDOFF_Z - 1, TOF_STANDOFF_Z + 3, 2.0))
    tof_cap = cq.Workplane("XY").center(0, TOF_Y).slot2D(12.0, 7.5, 0).extrude(3.2).translate((0, 0, TOF_STANDOFF_Z - 3.2))
    glass_win = box(-9.0, 9.0, TOF_Y - 9.0, TOF_Y + 9.0, 0.0, 0.5)

    # 2. DFRobot A02YYUW (SEN0311) at exact datasheet dimensions
    us_body = (
        cq.Workplane("XY")
        .center(0, US_Y)
        .rect(US_BODY_W, US_BODY_D)
        .extrude(US_BODY_H)
        .edges("|Z")
        .fillet(4.5)
        .translate((0, 0, US_SEAT_Z))
    )
    us_ears = (
        cq.Workplane("XY")
        .center(0, US_Y)
        .slot2D(US_EAR_SPAN, 12.0, 0)
        .extrude(US_EAR_T)
        .translate((0, 0, US_TOP_Z - US_EAR_T))
    )
    for sx in (-US_EAR_HOLE_DX, US_EAR_HOLE_DX):
        us_ears = us_ears.cut(cyl_z(sx, US_Y, US_TOP_Z - US_EAR_T - 1, US_TOP_Z + 1, 3.2))
    horns = []
    for sx in (-US_HORN_DX, US_HORN_DX):
        h_base = cyl_z(sx, US_Y, 2.0, US_SEAT_Z, US_HORN_BASE_D)
        h_tip = cyl_z(sx, US_Y, 0.0, 2.0, US_HORN_TIP_D)
        horns.append(h_base.union(h_tip))

    # Rear captive cable boot + exiting cable through the rear gland
    boot = cyl_y(0.0, US_Y + US_BODY_D / 2, US_Y + US_BODY_D / 2 + 10.0, US_SEAT_Z + 6.2, 7.0)
    cable = cyl_y(16.0, POD_H / 2 - 8.0, POD_H / 2 + 16.0, 13.5, 4.8)

    return [
        (glass_win, (0.45, 0.80, 0.95)),
        (tof_pcb, (0.14, 0.16, 0.20)),
        (tof_cap, (0.08, 0.08, 0.10)),
        (us_body.union(us_ears).union(boot), (0.16, 0.18, 0.22)),
        (horns[0], (0.25, 0.28, 0.32)),
        (horns[1], (0.25, 0.28, 0.32)),
        (cable, (0.20, 0.20, 0.22)),
    ]


def actor(shape, rgb, opacity=1.0, edges=False):
    vertices, faces = shape.val().tessellate(0.12, 0.2)
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


def render_png(path, items, cam_pos, focal=(0, 0, 10), up=(0, 0, 1), zoom=1.12):
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

    base = build_pod_base()
    cover = build_pod_cover()
    for name, solid in (("distance_pod_base", base), ("distance_pod_cover", cover)):
        cq.exporters.export(solid, str(OUT / f"{name}.step"), cq.exporters.ExportTypes.STEP)
        cq.exporters.export(solid, str(OUT / f"{name}.stl"), cq.exporters.ExportTypes.STL)
        print(f"distance_sensor_pod: exported {name}.step + {name}.stl")

    assy = base.union(cover)
    for s, _ in sensor_reference_solids():
        assy = assy.union(s)
    cq.exporters.export(assy, str(OUT / "distance_pod_assembly.step"), cq.exporters.ExportTypes.STEP)

    CASE = (0.82, 0.84, 0.88)
    LID_COL = (0.72, 0.76, 0.82)
    XRAY_BASE = (0.45, 0.58, 0.75)
    XRAY_LID = (0.35, 0.48, 0.68)
    sensors = sensor_reference_solids()
    sensor_actors = [(s, rgb, 1.0) for s, rgb in sensors]

    # 1. Transparent X-Ray Inside View
    render_png(RENDERS / "distance_pod_inside.png",
               [(base, XRAY_BASE, 0.22, True), (cover, XRAY_LID, 0.22, True)] + sensor_actors,
               (145, -170, 95), focal=(0, 0, 10), zoom=1.18)

    # 2. Cutaway Assembled View
    base_cut = base.cut(box(-24.0, 24.0, -40.0, -POD_H / 2 + WALL + 0.5, 4.0, POD_Z + 1))
    cover_cut = cover.intersect(box(-100, 100, 2.0, 100, -10, 40))
    render_png(RENDERS / "distance_pod_assembled.png",
               [(base_cut, CASE, 1.0), (cover_cut, LID_COL, 1.0)] + sensor_actors,
               (145, -170, 95), focal=(0, 0, 10), zoom=1.18)

    # 3. Exploded View
    exploded = [
        (base, CASE, 1.0),
        (sensors[0][0].translate((0, 0, -12)), sensors[0][1], 1.0),
        *[(s.translate((0, 0, 22)), rgb, 1.0) for s, rgb in sensors[1:]],
        (cover.translate((0, 0, 48)), LID_COL, 0.78, True),
    ]
    render_png(RENDERS / "distance_pod_exploded.png", exploded,
               (165, -190, 110), focal=(0, 0, 16), zoom=1.12)
    # 4. Bottom / Sensing-Face View (looking at z=0 to show the 18.4x18.4x0.7 mm
    #    recessed pocket for the 18x18 mm borosilicate glass slide + ultrasonic horns)
    render_png(RENDERS / "distance_pod_bottom.png",
               [(base, CASE, 1.0), (cover, LID_COL, 1.0)] + sensor_actors[1:],
               (115, -145, -90), focal=(0, -4, 4), up=(0, 0, 1), zoom=1.22)
    print(f"distance_sensor_pod renders saved to {RENDERS.relative_to(REPO)}")


if __name__ == "__main__":
    main()
