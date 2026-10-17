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

    # 4. Middle of the J305 glass tube (x=0, y=TUBE_Y, z=-23.0) is clear for Beta/Gamma
    for x_probe in (-25.0, 0.0, 25.0):
        assert not bracket.isInside(cq.Vector(x_probe, brd.TUBE_Y, -23.0))
        assert not bracket.isInside(cq.Vector(x_probe, brd.TUBE_Y, -30.0))
        assert not bracket.isInside(cq.Vector(x_probe, brd.TUBE_Y, -15.0))


def test_distance_pod_clamps_both_sensors_and_has_open_wire_port():
    base = bdp.build_pod_base().val()
    cover = bdp.build_pod_cover().val()

    assert base.Volume() > 8000
    assert cover.Volume() > 3000

    # 1. ToF Laser optical aperture at (0, TOF_Y, z=0..WALL) must be clear
    assert not base.isInside(cq.Vector(0.0, bdp.TOF_Y, bdp.WALL / 2))

    # 2. Both A02YYUW ultrasonic horn ports at (+-US_HORN_DX, US_Y, z=0..WALL) must be clear
    for sx in (-bdp.US_HORN_DX, bdp.US_HORN_DX):
        assert not base.isInside(cq.Vector(sx, bdp.US_Y, bdp.WALL / 2))

    # 3. Cover hold-down pillars reach down to clamp the VL53L1X PCB (z = TOF_STANDOFF_Z + TOF_PCB_T + 0.5)
    tof_top = bdp.TOF_STANDOFF_Z + bdp.TOF_PCB_T
    for sx in (-bdp.TOF_HOLE_DX, bdp.TOF_HOLE_DX):
        assert cover.isInside(cq.Vector(sx + 1.5, bdp.TOF_Y, tof_top + 0.5))

    # 4. Cover hold-down ribs reach down to clamp the A02YYUW ultrasonic body (z = US_SEAT_Z + US_BODY_H + 0.5)
    us_top = bdp.US_SEAT_Z + bdp.US_BODY_H
    for sx in (-15.5, 15.5):
        assert cover.isInside(cq.Vector(sx, bdp.US_Y, us_top + 0.5))

    # 5. Wire exit port on right wall (+x = POD_W/2 - WALL/2, y = -3.0, z = 14.0) is open
    assert not base.isInside(cq.Vector(bdp.POD_W / 2 - bdp.WALL / 2, -3.0, 14.0))
