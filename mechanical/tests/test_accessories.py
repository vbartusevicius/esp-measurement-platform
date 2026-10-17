"""Geometry, PCB-clearance, hold-down clamping, and wire-hole checks for the
plugin accessory enclosures:
  1. Radiation Counter CAJOE outer box + Curved In-Duct GM Tube Bracket
  2. Universal Distance Sensor Pod (VL53L1X ToF Laser + A02YYUW Sealed Ultrasonic)
"""

import sys
from pathlib import Path

import cadquery as cq

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "mechanical/scripts"))
import build_distance_pod as bdp
import build_radiation_duct as brd


def test_radiation_duct_cajoe_pcb_fits_without_corner_collision():
    base = brd.build_cajoe_base()
    cover = brd.build_cajoe_cover()
    bracket = brd.build_duct_tube_bracket().val()

    # 1. Verify the full 108 x 63 x 1.6 mm CAJOE PCB slab has zero collision with
    #    the base walls or lid screw bosses (only the 4 M3 locating pins pass through
    #    the 4 corner mounting holes)
    pcb_slab = brd.cajoe_board_and_tube_solids()[0][0]
    clash_base = base.intersect(pcb_slab).val().Volume()
    clash_cover = cover.intersect(pcb_slab).val().Volume()
    assert clash_base < 1e-3, f"CAJOE PCB collides with base ({clash_base:.2f} mm3)"
    assert clash_cover < 1e-3, f"CAJOE PCB collides with cover ({clash_cover:.2f} mm3)"

    # 2. Verify the cover's 4 hold-down pegs reach down to clamp the 4 corners of the CAJOE PCB
    cover_val = cover.val()
    pcb_top = brd.PCB_Z + brd.PCB_T
    for dx in (-brd.HOLE_DX, brd.HOLE_DX):
        for dy in (-brd.HOLE_DY, brd.HOLE_DY):
            sx = brd.PCB_X_SHIFT + dx
            assert cover_val.isInside(cq.Vector(sx + 2.0, dy, pcb_top + 0.5))

    # 3. Verify right-wall cable exit port is open at (x = BOX_W/2 - WALL/2, y = -8.0, z = PCB_Z + 7.0)
    base_val = base.val()
    assert not base_val.isInside(cq.Vector(brd.BOX_W / 2 - brd.WALL / 2, -8.0, brd.PCB_Z + 7.0))

    # 4. Verify all 3 HV wire channels (x = -42.0, +26.0 short, +44.0 long) are open
    #    and the central glass window (x = -25..+10) is clear for Beta/Gamma
    for sx in brd.TUBE_CRADLE_XS:
        assert not bracket.isInside(cq.Vector(sx, brd.TUBE_Y, -10.0))
        assert not base_val.isInside(cq.Vector(sx, brd.TUBE_Y, 0.0))
    for x_probe in (-25.0, -8.0, 10.0):
        assert not bracket.isInside(cq.Vector(x_probe, brd.TUBE_Y, -23.0))
        assert not bracket.isInside(cq.Vector(x_probe, brd.TUBE_Y, -30.0))
        assert not bracket.isInside(cq.Vector(x_probe, brd.TUBE_Y, -15.0))


def test_distance_pod_clamps_both_sensors_and_has_open_wire_port():
    base_wp = bdp.build_pod_base()
    cover_wp = bdp.build_pod_cover()
    base = base_wp.val()
    cover = cover_wp.val()

    assert base.Volume() > 8000
    assert cover.Volume() > 3000

    # 1. Verify ZERO collision between the exact-datasheet sensor solids
    #    (TOF400C-VL53L1X PCB + oval cap, A02YYUW body + 84.6mm ears + stepped horns)
    #    and both distance_pod_base and distance_pod_cover
    for idx, (sensor_solid, _) in enumerate(bdp.sensor_reference_solids()[1:6], start=1):
        clash_b = base_wp.intersect(sensor_solid).val().Volume()
        clash_c = cover_wp.intersect(sensor_solid).val().Volume()
        assert clash_b < 1e-3, f"Sensor solid #{idx} collides with pod base ({clash_b:.2f} mm3)"
        assert clash_c < 1e-3, f"Sensor solid #{idx} collides with pod cover ({clash_c:.2f} mm3)"

    # 2. ToF Laser optical aperture at (0, TOF_Y, z=0..WALL) must be clear
    assert not base.isInside(cq.Vector(0.0, bdp.TOF_Y, bdp.WALL / 2))

    # 3. Both A02YYUW ultrasonic horn ports at (+-US_HORN_DX = +-17.0 mm, US_Y) must be clear
    for sx in (-bdp.US_HORN_DX, bdp.US_HORN_DX):
        assert not base.isInside(cq.Vector(sx, bdp.US_Y, 1.0))
        assert not base.isInside(cq.Vector(sx, bdp.US_Y, 4.0))

    # 4. Cover hold-down blocks reach down to clamp the TOF400C / GY-530 PCB
    tof_top = bdp.TOF_STANDOFF_Z + bdp.TOF_PCB_T
    assert cover.isInside(cq.Vector(9.0, bdp.TOF_Y, tof_top + 0.5))
    assert cover.isInside(cq.Vector(-9.0, bdp.TOF_Y, tof_top + 0.5))

    # 5. Cover hold-down ribs reach down to clamp the A02YYUW ultrasonic body (z = US_TOP_Z + 0.5)
    for sx in (-bdp.US_HORN_DX, bdp.US_HORN_DX):
        assert cover.isInside(cq.Vector(sx, bdp.US_Y, bdp.US_TOP_Z + 0.5))

    # 6. Rear wire exit port at (x = 16.0, y = POD_H/2 - WALL/2, z = 13.5) is open
    assert not base.isInside(cq.Vector(16.0, bdp.POD_H / 2 - bdp.WALL / 2, 13.5))
