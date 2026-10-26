"""Optical dial reader housing (build_dial_reader.py): lock ring on the measured
dial hooks, rotatable carrier pressed by the ring's spring fingers, and the
routed `reader` PCB in the carrier."""

import json
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "mechanical/scripts"))
import build_dial_reader as m


def volume(shape):
    return sum(s.Volume() for s in shape.solids().vals())


def hook_overlap(shape):
    return sum(volume(shape.intersect(h)) for h in m.dial_hooks())


@pytest.fixture(scope="module")
def test_ring():
    return m.build_test_ring()


@pytest.fixture(scope="module")
def ring():
    return m.build_ring()


@pytest.fixture(scope="module")
def carrier():
    return m.build_carrier()


@pytest.fixture(scope="module")
def lid():
    return m.build_lid()


@pytest.fixture(scope="module")
def components():
    return {c["ref"]: c for c in json.loads(m.COMPONENTS.read_text())}


def test_printed_parts_are_single_bodies(ring, carrier, lid, test_ring):
    for shape in (ring, carrier, lid, test_ring):
        assert len(shape.solids().vals()) == 1


def test_housing_clears_the_rotating_white_ring(ring):
    bb = ring.val().BoundingBox()
    assert max(bb.xmax, -bb.xmin, bb.ymax, -bb.ymin) <= m.RING_ID / 2 - 0.2


def test_housing_is_low(ring, lid):
    assert ring.val().BoundingBox().zmax <= 15.5
    assert lid.val().BoundingBox().zmax <= 16.5          # incl. the grip bar and cable-tie bridge


@pytest.mark.parametrize("dz", [0, 1, 2, 4, 6])
def test_ring_drops_onto_the_glass_between_the_hooks(test_ring, dz):
    assert hook_overlap(m.rotated(test_ring, -m.LOCK_TURN).translate((0, 0, dz))) == 0


@pytest.mark.parametrize("deg", [-m.LOCK_TURN, -15, -10, -5, -2, 0])
def test_ring_turns_counter_clockwise_into_the_lock(test_ring, deg):
    assert hook_overlap(m.rotated(test_ring, deg)) == 0


def test_stop_ribs_end_the_turn(test_ring):
    assert hook_overlap(m.rotated(test_ring, 1.0)) > 1.0


def test_tabs_hold_under_the_hook_lips(test_ring):
    assert hook_overlap(test_ring.translate((0, 0, 0.4))) > 0.5


@pytest.mark.parametrize("deg", [0, 30, 75, 120, 200, 300])
def test_carrier_turns_freely_past_the_hooks(carrier, deg):
    assert hook_overlap(m.rotated(carrier, deg)) == 0


@pytest.fixture(scope="module")
def closed_carrier(carrier, lid):
    return carrier.union(lid)


@pytest.mark.parametrize("dz", [0, 2, 5, 9, 14, 20])
@pytest.mark.parametrize("deg", [-m.LOCK_TURN, -11, 0])
def test_ring_drops_straight_over_the_closed_carrier(closed_carrier, deg, dz):
    # the assembly path: the carrier is already on the glass, the ring comes down over it
    bare = m.build_ring(bumps=False)
    assert volume(m.rotated(bare, deg).translate((0, 0, dz)).intersect(closed_carrier)) == 0


@pytest.mark.parametrize("dz", [0, 3, 6, 12])
def test_closed_carrier_drops_between_the_hooks(closed_carrier, dz):
    assert hook_overlap(closed_carrier.translate((0, 0, dz))) == 0


def test_ring_touches_the_carrier_only_through_its_spring_bumps(closed_carrier):
    bare = m.build_ring(bumps=False)
    for deg in (-m.LOCK_TURN, 0):
        assert volume(m.rotated(bare, deg).translate((0, 0, 0.3)).intersect(closed_carrier)) == 0


def test_spring_bumps_press_the_lid_rim_with_the_tabs_against_the_lips(ring, lid):
    # tab top 0.3 mm under the lips: the ring can rise at most 0.3 mm
    assert volume(ring.translate((0, 0, 0.3)).intersect(lid)) > 0.5


def test_lid_fits_the_carrier(lid, carrier):
    assert volume(lid.intersect(carrier)) == 0


def test_pcb_and_parts_fit(carrier, lid):
    slab, parts = m.pcb_body()
    for name, solid in [("PCB", slab)] + parts:
        assert volume(solid.intersect(carrier)) < 0.01, f"{name} hits the carrier"
        assert volume(solid.intersect(lid)) < 0.01, f"{name} hits the lid"


def test_pcb_sits_on_rails_and_cannot_turn_in_the_carrier(carrier):
    slab, _ = m.pcb_body()
    assert volume(slab.translate((0, 0, -0.1)).intersect(carrier)) > 1.0
    assert volume(m.rotated(slab, 3).intersect(carrier)) > 0.5


def test_lid_posts_press_the_pcb(lid):
    slab, _ = m.pcb_body()
    assert volume(slab.translate((0, 0, 0.2)).intersect(lid)) > 0.1


def test_sensor_looks_at_the_half_disc_just_above_the_glass(components):
    u1 = components["U1"]
    assert u1["side"] == "back"
    assert 0.3 <= m.PCB_Z - u1["height"] <= 0.8
    b = u1["bbox"]
    cx, cy = (b["x0"] + b["x1"]) / 2 - m.PLAN_OFFSET[0], (b["y0"] + b["y1"]) / 2 - m.PLAN_OFFSET[1]
    long_y = (b["y1"] - b["y0"]) > (b["x1"] - b["x0"])
    for s in (-2.75, 2.75):
        x, y = (cx, cy + s) if long_y else (cx + s, cy)
        assert 2.0 <= math.hypot(x - m.WHEEL_X, y) <= m.WHEEL_D / 2 - 1.5


def test_lid_holes_over_led_and_trimmer_and_cable_hole_at_the_wire_entry(components):
    def centre(ref):
        b = components[ref]["bbox"]
        return (b["x0"] + b["x1"]) / 2 - m.PLAN_OFFSET[0], (b["y0"] + b["y1"]) / 2 - m.PLAN_OFFSET[1]
    for ref, xy in (("D2", m.LED_XY), ("RV1", m.TRIM_XY)):
        x, y = centre(ref)
        assert math.hypot(x - xy[0], y - xy[1]) < 0.6, ref
    entry_x = components["J1"]["bbox"]["x0"] - m.PLAN_OFFSET[0]
    assert m.CABLE_XY[0] - m.CABLE_HOLE[0] / 2 < entry_x - 1.0 < m.CABLE_XY[0] + m.CABLE_HOLE[0] / 2


def _probe(x, y, z0, z1, r=0.3):
    import cadquery as cq
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(r).extrude(z1 - z0)


def test_led_window_funnels_out_and_is_ringed(lid):
    x, y = m.LED_XY
    top = m.LID_Z + m.LID_T
    # open straight down to the LED, and 2.1 mm off-axis at the top surface (seen from the side)
    assert volume(lid.intersect(_probe(x, y, m.LID_Z - 0.5, top + m.LED_RING_H + 0.5, r=1.1))) == 0
    assert volume(lid.intersect(_probe(x + 2.1, y, top - 0.15, top + 0.5, r=0.15))) == 0
    # solid at the bottom of that off-axis spot: the hole is a funnel, not a big hole over other parts
    assert volume(lid.intersect(_probe(x + 2.1, y, m.LID_Z + 0.05, m.LID_Z + 0.3, r=0.15))) > 0
    # raised ring around the window, below the grip bar
    assert volume(lid.intersect(_probe(x + 2.9, y, top + 0.1, top + m.LED_RING_H - 0.1, r=0.3))) > 0
    assert top + m.LED_RING_H < top + 2.0


def test_set_label_is_engraved_beside_the_trimmer_and_clear_of_holes(lid):
    import cadquery as cq
    top = m.LID_Z + m.LID_T
    x, y = m.SET_XY
    label_zone = cq.Workplane("XY").workplane(offset=top - m.SET_DEPTH).center(x, y).rect(4.6, 2.2).extrude(m.SET_DEPTH)
    solid_full = 4.6 * 2.2 * m.SET_DEPTH
    removed = solid_full - volume(lid.intersect(label_zone))
    assert 0.1 * solid_full < removed < 0.8 * solid_full       # letters cut, not a pocket
    # the label stays clear of the trimmer hole and the grip bar
    assert x + 2.3 < m.TRIM_XY[0] - 1.9
    assert y - 1.1 > -4.5
