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


def test_oled_window_clear(solids):
    win = ef.oled_window()
    assert clear_line(solids, win["cx"], win["cy"], be.FRONT_INNER_Z - 0.2, be.TOTAL_D + 1)


def test_button_tabs_spring_on_a_c_slot_with_bump_and_plunger(solids):
    t = be.BUTTON_TAB
    for name, h in ef.button_holes().items():
        ref = "SW1" if name == "PROG" else "SW2"
        s = 1 if h["x"] > 0 else -1
        ring = t["pad"] / 2 + t["slot"] / 2
        # C-slot open around the pad (outboard, above, below) and along the arm
        for px, py in ((h["x"] + s * ring, h["y"]), (h["x"], h["y"] + ring), (h["x"], h["y"] - ring),
                       ((h["x"] + s * t["root_x"]) / 2, h["y"] + t["arm"] / 2 + t["slot"] / 2)):
            assert clear_line(solids, px, py, be.FRONT_INNER_Z - 0.2, be.TOTAL_D + 0.2), (name, px, py)
        # pad thinned behind, bump in front, plunger ending just above the actuator
        assert not solid_at(solids, h["x"] + s * 1.0, h["y"], be.TOTAL_D - t["thickness"] - 0.1)
        assert solid_at(solids, h["x"], h["y"], be.TOTAL_D + t["boss_height"] / 2)
        top = be.button_top_z(ref)
        assert solid_at(solids, h["x"], h["y"], top + t["nub_gap"] + 0.1)
        assert not solid_at(solids, h["x"], h["y"], top + t["nub_gap"] - 0.05)


def test_oled_panel_seats_in_its_pocket(solids):
    p = ef.oled_panel_real()
    for fx in (0.02, 0.5, 0.98):
        for fy in (0.02, 0.5, 0.98):
            x = p["cx"] - p["w"] / 2 + p["w"] * fx
            y = p["cy"] - p["h"] / 2 + p["h"] * fy
            assert clear_line(solids, x, y, p["z0"] + 0.02, p["z1"] - 0.02, steps=4), (x, y)
    # pocket floor in front of the panel edge holds it (outside the window)
    assert solid_at(solids, p["cx"] - p["w"] / 2 + 0.5, p["cy"], p["z1"] + 0.2)


def test_terminal_slots_open_to_the_left_for_board_insertion(solids):
    base = solids[0]
    for s in ef.wire_entries():
        y = be.WALL / 2 if s.get("side") == "bottom" else ef.HIDDEN_H - be.WALL / 2
        z = (s["z0"] + s["z1"]) / 2
        for x in (-ef.WIDTH / 2 + 0.3, s["x0"] - 1.0, s["x0"] + 0.5):
            assert not base.isInside(cq.Vector(x, y, z)), (s["ref"], x)


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
    solids = solids[:1]  # the cover's slot fillers sit left of the terminal bodies only
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
            # board ends and edges too, not only the centre
            for y in (s["y0"] + 0.05, s["y1"] - 0.05):
                for z in (s["z0"] + 0.05, s["z1"] - 0.05):
                    assert not solid_at(solids, cx, y, z), (board, y, z)


def test_main_board_has_fdm_clearance_to_the_end_walls():
    s = ef.board_slab("main")
    assert s["y0"] - be.WALL >= be.FDM_CLEAR - 1e-6
    assert (ef.HIDDEN_H - be.WALL) - s["y1"] >= be.FDM_CLEAR - 1e-6


def test_ui_board_is_located_on_all_sides(solids):
    s = ef.board_slab("ui")
    cz = (s["z0"] + s["z1"]) / 2
    gap = be.UI_RIB["gap"]
    for y in be.UI_RIB["side_ys"]:
        assert solid_at(solids, s["x1"] + gap + 0.1, y, cz) and solid_at(solids, s["x0"] - gap - 0.1, y, cz)
    for x in be.UI_RIB["end_xs"]:
        assert solid_at(solids, x, s["y0"] - gap - 0.1, cz) and solid_at(solids, x, s["y1"] + gap + 0.1, cz)


def test_cover_side_wall_clears_the_base_walls(solids):
    """Where the base wall is intact (outside the terminal slots and their
    filler ties) the cover's side wall keeps FDM_CLEAR to it."""
    cover = solids[1]
    x = -ef.WIDTH / 2 + 0.3  # outer skin left behind the THT-tail recesses
    slots = be.terminal_slots()

    def free_z(side):
        covered = [(s["z0"], s["z1"]) for s in slots if s["side"] == side] + [(8.8, 14.2)]  # + snap keepers
        return next(z for z in (z / 10 for z in range(30, 420, 5))
                    if z > be.WALL + 1 and all(not (a - 0.3 <= z <= b + 0.3) for a, b in covered))

    zb, zt = free_z("bottom"), free_z("top") if any(s["side"] == "top" for s in slots) else 20.0
    assert not cover.isInside(cq.Vector(x, be.WALL + be.FDM_CLEAR / 2, zb)), zb
    assert not cover.isInside(cq.Vector(x, ef.HIDDEN_H - be.WALL - be.FDM_CLEAR / 2, zt)), zt
    assert cover.isInside(cq.Vector(x, ef.HIDDEN_H / 2, 20.0))
