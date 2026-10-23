"""Fit, retention and assembly checks for the wall-mount box (build_box_enclosure.py)."""

import math
import sys
from functools import lru_cache
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "mechanical/scripts"))
sys.path.insert(0, str(REPO / ".claude/skills/manufacturing-readiness-review/scripts"))
import build_box_enclosure as bx
import enclosure_features as ef
from build_enclosure import box

EPS = 1e-3


@lru_cache(maxsize=None)
def parts():
    return bx.build_base(), bx.build_lid()


def envelopes():
    """Board slabs and every component envelope, in box coordinates."""
    items = [("main board", ef.board_slab("main"))] + [(p["ref"], p) for p in bx.MAIN_PARTS]
    a = bx.point_to_box(*(ef.board_slab("ui")[k] for k in ("x0", "y0", "z0")))
    b = bx.point_to_box(*(ef.board_slab("ui")[k] for k in ("x1", "y1", "z1")))
    slab = {"x0": min(a[0], b[0]), "x1": max(a[0], b[0]), "y0": min(a[1], b[1]), "y1": max(a[1], b[1]),
            "z0": min(a[2], b[2]), "z1": max(a[2], b[2])}
    return items + [("ui board", slab)] + [("ui " + p["ref"], p) for p in bx.ui_parts_box()]


def solid(b, grow_x1=0.0):
    return box(b["x0"], b["x1"] + grow_x1, b["y0"], b["y1"], b["z0"], b["z1"])


def overlap(a, b):
    common = a.intersect(b)
    return sum(s.Volume() for s in common.solids().vals()) if common.solids().vals() else 0.0


def test_overlap_check_detects_a_real_clash():
    base, _ = parts()
    probe = box(bx.XB - 1, bx.XB + 1, 30, 35, 10, 15)   # through the back wall
    assert overlap(base, probe) > 1.0


@pytest.mark.parametrize("index", [0, 1], ids=["base", "lid"])
def test_part_is_one_valid_solid(index):
    shape = parts()[index].val()
    assert shape.isValid()
    assert len(parts()[index].solids().vals()) == 1


@pytest.mark.parametrize("index", [0, 1], ids=["base", "lid"])
def test_no_board_or_component_inside_the_case(index):
    clashes = [(name, round(v, 3)) for name, b in envelopes() if (v := overlap(parts()[index], solid(b))) > EPS]
    assert not clashes


def test_base_and_lid_do_not_overlap():
    base, lid = parts()
    assert overlap(base, lid) <= EPS


@pytest.mark.parametrize("lift", [0.5, 2.0, 6.0, 12.0])
def test_lid_mates_straight_down(lift):
    base, lid = parts()
    assert overlap(base, lid.translate((lift, 0, 0))) <= EPS


def test_populated_main_board_drops_straight_in():
    """Sweep the board and its parts along +x out of the tray: nothing in the base is in the way."""
    base, _ = parts()
    sweep = 60.0
    blocked = [(name, round(v, 3)) for name, b in envelopes()[: len(bx.MAIN_PARTS) + 1]
               if (v := overlap(base, solid(b, grow_x1=sweep))) > EPS]
    assert not blocked


def test_main_board_is_held_in_all_directions():
    main = ef.board_slab("main")
    base, _ = parts()
    # -x: the posts end on the board back; +x: lid filler bars over every terminal body
    for y, z in bx.POSTS:
        assert overlap(base, box(main["x0"] - 0.05, main["x0"], y - 0.5, y + 0.5, z - 0.5, z + 0.5)) > 0.0, (y, z)
    for o, bar in zip(bx.terminal_openings(), bx.filler_bars()):
        gap = bar.val().BoundingBox().xmin - o["top_x"]
        assert 0.1 <= gap <= 0.3, (o["ref"], gap)
    # +-y: board ends to the top/bottom walls; +-z: terminal bodies in their openings
    assert 0.1 <= main["y0"] - bx.WALL <= 0.3 and 0.1 <= (bx.H - bx.WALL) - main["y1"] <= 0.3
    for o in bx.terminal_openings():
        assert o["z0"] < o["z1"]


def test_posts_touch_the_board_back_clear_of_solder_tails():
    main = ef.board_slab("main")
    for y, z in bx.POSTS:
        for comp in ef.components("main").values():
            for px, py in comp.get("tht_pads", []):
                _, ty, tz = ef.board_point("main", px, py)
                assert math.hypot(ty - y, tz - z) >= bx.POST_D / 2 + 1.0, (comp["ref"], y, z)
        assert main["y0"] + 2 <= y <= main["y1"] - 2 and main["z0"] + 2 <= z <= main["z1"] - 2


def test_ui_board_sits_above_the_main_parts():
    ui_back = min(p["x0"] for p in bx.ui_parts_box())
    assert ui_back - max(p["x1"] for p in bx.MAIN_PARTS) >= bx.UI_GAP - 0.01


def test_ui_board_is_snapped_and_located():
    t = bx.SNAP_ARM
    assert t["x_in"] - ef.UI_W / 2 >= 0.3            # arm clear of the board edge and OLED panel
    assert t["overlap"] >= 0.4                       # hook catches the board back
    assert bx.UI_BLOCK["gap"] <= 0.2                 # buttons / LEDs within 0.3 mm of their windows


def test_ffc_reaches_between_the_boards():
    main_j3 = next(p for p in bx.MAIN_PARTS if p["ref"] == "J3")
    ui_j1 = next(p for p in bx.ui_parts_box() if p["ref"] == "J1")
    c = lambda p: ((p["x0"] + p["x1"]) / 2, (p["y0"] + p["y1"]) / 2, (p["z0"] + p["z1"]) / 2)
    a, b = c(main_j3), c(ui_j1)
    folded_route = sum(abs(u - v) for u, v in zip(a, b))   # along the axes, i.e. with right-angle folds
    assert folded_route <= 50.0 - 8.0 - 4.0               # 50 mm cable, 4 mm in each connector, 4 mm slack


def test_terminal_legend_stays_clear_of_the_ui_openings():
    _, cuts, _ = bx.ui_front_features()
    legend = bx.terminal_legend()
    face = bx.box(bx.XI, bx.XF + 1, 0, bx.H, bx.Z0, bx.Z1)
    near = [round(legend.val().distance(bx.to_box(c).intersect(face).val()), 2) for c in cuts
            if bx.to_box(c).intersect(face).solids().vals()]
    assert min(near) >= 3.0


def test_ui_labels_stay_clear_of_the_terminal_legend():
    assert bx.ui_legend().val().distance(bx.terminal_legend().val()) >= 3.0


def test_released_meshes_are_watertight_single_bodies(tmp_path):
    import mesh_audit
    bx.export_parts(tmp_path)
    for name in ("box_base", "box_lid"):
        bodies, open_edges, nonmanifold = mesh_audit.bodies(mesh_audit.read_stl(tmp_path / f"{name}.stl"))
        assert (len(bodies), open_edges, nonmanifold) == (1, 0, 0), name
