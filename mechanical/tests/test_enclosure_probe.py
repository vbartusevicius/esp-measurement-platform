"""Probe the generated 1-DIN Universal Sensor Node case solids (base and cover)."""

import math
import sys
from pathlib import Path

import cadquery as cq
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "mechanical/scripts"))
import build_enclosure as be
import enclosure_features as ef


@pytest.fixture(scope="module")
def solids():
    return be.build_base().val(), be.build_cover().val()


def solid_at(solids, x, y, z):
    return any(s.isInside(cq.Vector(x, y, z)) for s in solids)


def clear_line(solids, x, y, z0, z1, steps=12):
    return not any(solid_at(solids, x, y, z0 + (z1 - z0) * i / steps) for i in range(steps + 1))


def test_front_openings_clear(solids):
    holes = list(ef.button_holes().values())
    win = ef.oled_window()
    holes.append({"x": win["cx"], "y": win["cy"]})
    blocked = [h for h in holes if not clear_line(solids, h["x"], h["y"], be.FRONT_INNER_Z - 0.2, be.TOTAL_D + 1)]
    assert not blocked


def test_led_windows_are_thin_skins_over_open_pockets(solids):
    skin = be.STACK.led_skin_mm
    for w in ef.led_windows():
        assert solid_at(solids, w["x"], w["y"], be.TOTAL_D - skin / 2)
        assert not solid_at(solids, w["x"], w["y"], be.TOTAL_D - skin - 0.1)
        assert clear_line(solids, w["x"], w["y"], be.STACK.led_top_z + 0.05, be.TOTAL_D - skin - 0.1)


def test_each_led_sits_in_a_closed_baffle(solids):
    radius = be.LED_WINDOW / 2 + be.BAFFLE_WALL / 2
    z = (be.STACK.baffle_bottom_z + be.FRONT_INNER_Z) / 2
    for w in ef.led_windows():
        for k in range(12):
            a = 2 * math.pi * k / 12
            assert solid_at(solids, w["x"] + radius * math.cos(a), w["y"] + radius * math.sin(a), z)


def test_terminal_faces_open_in_top_and_bottom_walls(solids):
    for s in ef.wire_entries():
        y_probe = be.WALL / 2 if s.get("side") == "bottom" else ef.HIDDEN_H - be.WALL / 2
        for fx in (0.2, 0.5, 0.8):
            for fz in (0.2, 0.5, 0.8):
                x = s["x0"] + (s["x1"] - s["x0"]) * fx
                z = s["z0"] + (s["z1"] - s["z0"]) * fz
                assert not solid_at(solids, x, y_probe, z), s["ref"]


def test_no_material_inside_the_boards(solids):
    for board in ef.SPEC["variants"][ef.VARIANT]["boards"]:
        for s in ef.board_slabs(board):
            cx = (s["x0"] + s["x1"]) / 2
            cy = (s["y0"] + s["y1"]) / 2
            cz = (s["z0"] + s["z1"]) / 2
            assert not solid_at(solids, cx, cy, cz), board
