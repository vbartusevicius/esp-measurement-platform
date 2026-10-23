"""Renders and assembly STEP of the wall-mount box (VTK, offscreen).

Writes mechanical/build/<variant>-box/box_assembly.step and renders/box_*.png.
"""

import sys
from pathlib import Path

import cadquery as cq
import vtk

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "mechanical/scripts"))
import build_box_enclosure as bx
import enclosure_features as ef
import render_assembly3d as ra


def ui_transform(lift=0.0):
    t = vtk.vtkTransform()
    t.Translate(bx.XF - ef.TOTAL_D + lift, bx.DY, bx.ZC)
    t.RotateY(90)
    return t


def scene():
    plates = ra.board_plates()
    boards = [(p if c == ra.MAIN else bx.to_box(p), c, 1.0) for p, c in plates]
    main_parts, ui_parts = [], []
    for shape, rgb, board, _ in ra.part_solids():
        (main_parts if board == "main" else ui_parts).append((shape if board == "main" else bx.to_box(shape), rgb, 1.0))
    return boards, main_parts, ui_parts


def main():
    renders = bx.OUT / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    ra.RENDERS = renders
    base, lid = bx.build_base(), bx.build_lid()
    legend = bx.legend()
    boards, main_parts, ui_parts = scene()

    assembly = base.union(lid)
    for plate, _, _ in boards:
        assembly = assembly.union(plate)
    cq.exporters.export(assembly, str(bx.OUT / "box_assembly.step"), cq.exporters.ExportTypes.STEP)
    print("box_assembly.step saved")

    oled = ra.oled_pixels_actor(0.0)
    oled.SetUserTransform(ui_transform())
    shell = [(base, ra.CASE, 1.0), (lid, ra.CASE, 1.0), (legend, (0.10, 0.10, 0.12), 1.0)]
    inside = boards + main_parts + ui_parts
    centre = (bx.XF / 2, bx.H / 2, bx.ZC)
    ra.render("box_front", shell + inside, (300, bx.H / 2, bx.ZC), focal=centre, zoom=1.15, extra_actors=(oled,))
    ra.render("box_iso", shell + inside, (190, 150, 170), focal=centre, extra_actors=(oled,))
    ra.render("box_back", [(base, ra.CASE, 1.0)], (-200, 120, -60), focal=centre)
    ra.render("box_inside", [(base, ra.CASE, 0.12), (lid, ra.CASE, 0.12)] + inside, (190, 150, 170), focal=centre,
              extra_actors=(oled,))
    lift = 35.0
    exploded_oled = ra.oled_pixels_actor(0.0)
    exploded_oled.SetUserTransform(ui_transform(lift))
    shifted = lambda items, dx: [(s.translate((dx, 0, 0)), c, o) for s, c, o in items]
    ra.render("box_exploded", [(base, ra.CASE, 1.0)] + [b for b in boards if b[1] == ra.MAIN] + main_parts
              + shifted([b for b in boards if b[1] == ra.UI] + ui_parts, lift)
              + shifted([(lid, ra.CASE, 0.4), (legend, (0.10, 0.10, 0.12), 0.85)], 2 * lift),
              (230, 160, 150), focal=(lift, bx.H / 2, bx.ZC), extra_actors=(exploded_oled,))


if __name__ == "__main__":
    main()
