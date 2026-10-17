"""CadQuery Universal Distance Sensor Pod (supports BOTH ToF Laser VL53L1X/TOF200C
AND Sealed Dual-Transducer Waterproof Ultrasonic A02YYUW / SEN0388).

Key mechanical features:
  1. Bay 1 (Front, y = -13.0 mm): Optical ToF Laser module (VL53L1X / TOF200C,
     25 x 11.5 x 1.6 mm PCB, 19.6 mm M2.5 hole pitch, 0-200 cm range, zero blind zone).
     Sits over an 8 x 5 mm optical aperture with an 18.4 x 18.4 x 0.6 mm outer
     pocket for a standard 18 x 18 mm (#1.5, 0.17 mm) borosilicate microscope
     cover slip (or ST VL53L1X anti-crosstalk PMMA optical cap).
  2. Bay 2 (Rear, y = +8.0 mm): Sealed Dual-Transducer Waterproof Ultrasonic
     sensor (A02YYUW / SEN0388, 56 x 24 x 11 mm body, 2 x D=14.5 mm sealed horns
     at 31.0 mm pitch, 3-450 cm range), seated in twin D=15.4 mm downward collars.
  3. Positive Hold-Down Clamping from the Cover (zero loose sensors):
     - Two compression pillars with D=1.9 mm locating tips hang from the cover
       directly onto the VL53L1X PCB's mounting holes, clamping the laser PCB
       against the base standoffs when the cover is closed.
     - Two compression ribs + ear pins hang from the cover onto the top of the
       A02YYUW body, locking the ultrasonic horns firmly into the bottom collars.
  4. Wire Exit Port + Strain Relief:
     - D=6.5 mm round cable entry port on the right wall (+x) with an internal
       cable saddle + zip-tie slots for the 4-wire cable (+5V, GND, IO1, IO2).

Outputs under hardware/releases/v1/accessories/distance_sensor_pod/:
  - distance_pod_base.stl / .step
  - distance_pod_cover.stl / .step
  - distance_pod_assembly.step
  - renders/distance_pod_inside.png (transparent view), distance_pod_assembled.png,
    distance_pod_exploded.png
"""

from pathlib import Path

import cadquery as cq
import vtk

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "hardware/releases/v1/accessories/distance_sensor_pod"
RENDERS = OUT / "renders"

WALL = 2.0
POD_W = 76.0
POD_H = 52.0
POD_Z = 22.0
LID_T = 2.4

# Bay 1: VL53L1X / TOF200C ToF Laser sensor (y = -13.0)
TOF_Y = -13.0
TOF_HOLE_DX = 9.8
TOF_STANDOFF_Z = WALL + 3.2   # 5.2 mm
TOF_PCB_T = 1.6               # top of ToF PCB at z = 6.8 mm

# Bay 2: A02YYUW Dual-Transducer Sealed Ultrasonic (y = +8.0)
US_Y = 8.0
US_HORN_DX = 15.5
US_HORN_DIA = 15.4
US_MOUNT_DX = 26.0
US_SEAT_Z = WALL + 5.5        # 7.5 mm
US_BODY_H = 11.0              # top of A02YYUW body at z = 18.5 mm


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def cyl_z(x, y, z0, z1, d):
    return cq.Workplane("XY").circle(d / 2).extrude(z1 - z0).translate((x, y, z0))


def cyl_x(x0, x1, y, z, d):
    return cq.Workplane("YZ", origin=(x0, 0, 0)).center(y, z).circle(d / 2).extrude(x1 - x0)


def build_pod_base():
    hw, hh = POD_W / 2, POD_H / 2
    shell = box(-hw, hw, -hh, hh, 0, POD_Z).cut(
        box(-hw + WALL, hw - WALL, -hh + WALL, hh - WALL, WALL, POD_Z + 1)
    )

    # Side mounting flanges (screw onto the tank lid)
    for s in (-1, 1):
        ear = box(s * hw - (0 if s > 0 else 9.0), s * hw + (9.0 if s > 0 else 0), -15.0, 15.0, POD_Z - 3.2, POD_Z)
        for ey in (-8.5, 8.5):
            ear = ear.cut(cyl_z(s * (hw + 4.5), ey, POD_Z - 4.0, POD_Z + 1.0, 4.2))
        shell = shell.union(ear)

    # 4 corner lid screw bosses
    for sx in (-hw + WALL + 2.8, hw - WALL - 2.8):
        for sy in (-hh + WALL + 2.8, hh - WALL - 2.8):
            boss = cyl_z(sx, sy, WALL, POD_Z, 5.6).cut(cyl_z(sx, sy, POD_Z - 12.0, POD_Z + 1, 2.4))
            shell = shell.union(boss)

    # --- Bay 1 (y = TOF_Y): VL53L1X / TOF200C ToF Laser ---
    # 10 x 6 mm optical aperture + 18.4 x 18.4 x 0.8 mm recess for 18x18 mm cover glass
    shell = shell.cut(box(-5.0, 5.0, TOF_Y - 3.0, TOF_Y + 3.0, -1.0, WALL + 1.0))
    shell = shell.cut(box(-9.2, 9.2, TOF_Y - 9.2, TOF_Y + 9.2, -0.1, 0.8))
    for sx in (-TOF_HOLE_DX, TOF_HOLE_DX):
        post = cyl_z(sx, TOF_Y, WALL, TOF_STANDOFF_Z, 5.2)
        shell = shell.union(post)

    # --- Bay 2 (y = US_Y): A02YYUW Sealed Dual-Transducer Ultrasonic ---
    for sx in (-US_HORN_DX, US_HORN_DX):
        collar = cyl_z(sx, US_Y, WALL, US_SEAT_Z, US_HORN_DIA + 3.4)
        shell = shell.union(collar).cut(cyl_z(sx, US_Y, -1.0, US_SEAT_Z + 1.0, US_HORN_DIA))
    for sx in (-US_MOUNT_DX, US_MOUNT_DX):
        post = cyl_z(sx, US_Y, WALL, US_SEAT_Z, 5.4)
        shell = shell.union(post)

    # --- Wire Exit Port (D=6.5 mm round gland hole on right wall + internal cable saddle) ---
    cable_y, cable_z = -3.0, 14.0
    gland_boss = cyl_x(hw - WALL - 1.5, hw + 2.5, cable_y, cable_z, 10.5)
    shell = shell.union(gland_boss).cut(cyl_x(hw - WALL - 3.0, hw + 4.0, cable_y, cable_z, 6.2))
    # Internal strain-relief tie-down saddle at x = hw - 7.5
    saddle = box(hw - 9.5, hw - 4.5, cable_y - 4.5, cable_y + 4.5, WALL, cable_z - 3.0)
    saddle = saddle.cut(box(hw - 8.5, hw - 5.5, cable_y - 5.0, cable_y + 5.0, WALL + 1.5, cable_z - 4.5))
    shell = shell.union(saddle)

    return shell


def build_pod_cover():
    """Cover with integrated hold-down pillars & ribs that clamp BOTH the
    VL53L1X ToF laser PCB and the A02YYUW ultrasonic body tight when closed."""
    hw, hh = POD_W / 2, POD_H / 2
    lid = box(-hw, hw, -hh, hh, POD_Z, POD_Z + LID_T)
    lip = box(-hw + WALL + 0.25, hw - WALL - 0.25, -hh + WALL + 0.25, hh - WALL - 0.25, POD_Z - 1.6, POD_Z).cut(
        box(-hw + WALL + 1.6, hw - WALL - 1.6, -hh + WALL + 1.6, hh - WALL - 1.6, POD_Z - 2.0, POD_Z + 1)
    )
    lid = lid.union(lip)

    # 1. Hold-down compression pillars + locating pins for VL53L1X ToF Laser PCB
    tof_top = TOF_STANDOFF_Z + TOF_PCB_T  # 6.8 mm
    for sx in (-TOF_HOLE_DX, TOF_HOLE_DX):
        # Shoulder presses onto top of ToF PCB (z = 6.9..POD_Z); pin goes through M2.5 hole
        pillar = cyl_z(sx, TOF_Y, tof_top + 0.1, POD_Z + 0.1, 4.8)
        pin = cyl_z(sx, TOF_Y, TOF_STANDOFF_Z + 0.2, tof_top + 0.2, 1.9)
        lid = lid.union(pillar).union(pin)

    # 2. Hold-down compression ribs + ear pins for A02YYUW Ultrasonic sensor
    us_top = US_SEAT_Z + US_BODY_H  # 18.5 mm
    for sx in (-15.5, 15.5):
        rib = box(sx - 4.0, sx + 4.0, US_Y - 8.0, US_Y + 8.0, us_top + 0.1, POD_Z + 0.1)
        lid = lid.union(rib)
    for sx in (-US_MOUNT_DX, US_MOUNT_DX):
        ear_clamp = cyl_z(sx, US_Y, US_SEAT_Z + 2.2, POD_Z + 0.1, 4.8)
        ear_pin = cyl_z(sx, US_Y, US_SEAT_Z + 0.2, US_SEAT_Z + 2.4, 1.9)
        lid = lid.union(ear_clamp).union(ear_pin)

    # 4 corner screw clearance holes
    for sx in (-hw + WALL + 2.8, hw - WALL - 2.8):
        for sy in (-hh + WALL + 2.8, hh - WALL - 2.8):
            lid = lid.cut(cyl_z(sx, sy, POD_Z - 3.0, POD_Z + LID_T + 1, 3.0))

    return lid


def sensor_reference_solids():
    """Reference 3D solids for the VL53L1X ToF laser module, cover glass,
    A02YYUW sealed ultrasonic sensor, and exiting 4-wire sensor cable."""
    # 1. VL53L1X / TOF200C PCB + optical IC + 18x18 mm borosilicate cover glass
    tof_pcb = box(-12.5, 12.5, TOF_Y - 5.6, TOF_Y + 5.6, TOF_STANDOFF_Z, TOF_STANDOFF_Z + TOF_PCB_T)
    for sx in (-TOF_HOLE_DX, TOF_HOLE_DX):
        tof_pcb = tof_pcb.cut(cyl_z(sx, TOF_Y, TOF_STANDOFF_Z - 1, TOF_STANDOFF_Z + 3, 2.4))
    tof_ic = box(-3.2, 3.2, TOF_Y - 1.8, TOF_Y + 1.8, TOF_STANDOFF_Z - 1.4, TOF_STANDOFF_Z)
    glass_win = box(-9.0, 9.0, TOF_Y - 9.0, TOF_Y + 9.0, 0.0, 0.6)

    # 2. A02YYUW Dual-Transducer Sealed Ultrasonic (56 x 23 mm body + mounting ears + horns)
    us_body = box(-23.0, 23.0, US_Y - 11.0, US_Y + 11.0, US_SEAT_Z, US_SEAT_Z + US_BODY_H)
    us_ears = box(-28.5, 28.5, US_Y - 4.0, US_Y + 4.0, US_SEAT_Z, US_SEAT_Z + 2.0)
    for sx in (-US_MOUNT_DX, US_MOUNT_DX):
        us_ears = us_ears.cut(cyl_z(sx, US_Y, US_SEAT_Z - 1, US_SEAT_Z + 4, 2.4))
    horn_l = cyl_z(-US_HORN_DX, US_Y, 0.2, US_SEAT_Z, 14.6)
    horn_r = cyl_z(US_HORN_DX, US_Y, 0.2, US_SEAT_Z, 14.6)

    # 3. 4-wire cable exiting through the right-wall gland boss
    cable = cyl_x(POD_W / 2 - 8.0, POD_W / 2 + 16.0, -3.0, 14.0, 4.8)

    return [
        (glass_win, (0.45, 0.80, 0.95)),
        (tof_pcb, (0.58, 0.14, 0.62)),
        (tof_ic, (0.12, 0.12, 0.14)),
        (us_body.union(us_ears), (0.16, 0.18, 0.22)),
        (horn_l, (0.25, 0.28, 0.32)),
        (horn_r, (0.25, 0.28, 0.32)),
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

    # 1. Transparent X-Ray Inside View (shows hold-down pegs clamping both sensors + wire exit)
    render_png(RENDERS / "distance_pod_inside.png",
               [(base, XRAY_BASE, 0.22, True), (cover, XRAY_LID, 0.22, True)] + sensor_actors,
               (125, -145, 80), focal=(2, 0, 10), zoom=1.18)

    # 2. Cutaway Assembled View
    base_cut = base.cut(box(-24.0, 24.0, -30.0, -POD_H / 2 + WALL + 0.5, 5.0, POD_Z + 1))
    cover_cut = cover.intersect(box(-100, 100, 2.0, 100, -10, 40))
    render_png(RENDERS / "distance_pod_assembled.png",
               [(base_cut, CASE, 1.0), (cover_cut, LID_COL, 1.0)] + sensor_actors,
               (125, -145, 85), focal=(2, 0, 10), zoom=1.18)

    # 3. Exploded View (turned so the upside-down cover's hold-down pillars are visible)
    exploded = [
        (base, CASE, 1.0),
        (sensors[0][0].translate((0, 0, -12)), sensors[0][1], 1.0),
        *[(s.translate((0, 0, 20)), rgb, 1.0) for s, rgb in sensors[1:]],
        (cover.translate((0, 0, 44)), LID_COL, 0.78, True),
    ]
    render_png(RENDERS / "distance_pod_exploded.png", exploded,
               (145, -165, 95), focal=(2, 0, 16), zoom=1.12)
    print(f"distance_sensor_pod renders saved to {RENDERS.relative_to(REPO)}")


if __name__ == "__main__":
    main()
