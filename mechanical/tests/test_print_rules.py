"""Defects the sister project knx-dali-gateway found on its first powder-printed
(MJF / SLS) 1-DIN case of the same design (2026-11-09): a cover lip held only by
the snap tongues, a DIN latch fused to the base with a spring too stiff to
release, smeared small legend text, connector names on the front instead of
beside the connectors, unreachable top-face terminal releases, the main board
resting on a capacitor, a side wall that dented between its supports, and a
cover that pivoted on four clicks. Each test keeps one of them from coming back
here; several also check that the old geometry would have failed.
"""

import sys
from itertools import pairwise
from pathlib import Path

import cadquery as cq
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "mechanical/scripts"))
import build_enclosure as be
import enclosure_features as ef
import front_legend as fl
import legend_engraving as le


@pytest.fixture(scope="module")
def solids():
    return be.build_base().val(), be.build_cover().val()


def inside(shape, x, y, z):
    return shape.isInside(cq.Vector(x, y, z))


# 1. Lip bonded to the wall, snap tongues free


def test_cover_lip_is_bonded_to_the_side_wall_along_its_length(solids):
    """The knx lip hung 0.15 mm inside the wall and held on only at the snap tongues."""
    _, cover = solids
    lip_x = be.INNER_W / 2 - 0.15 - be.LIP["thickness"] / 2
    z_lip, z_bond = ef.BASE_TOP_Z - be.LIP["depth"] / 2, ef.BASE_TOP_Z + be.LIP_BOND["height"] / 2
    ys = [y / 4 for y in range(int(4 * be.WALL) + 4, int(4 * (ef.HIDDEN_H - be.WALL)) - 4)]
    lip_ys = [y for y in ys if inside(cover, lip_x, y, z_lip)]
    assert len(lip_ys) > 100, "no lip"
    loose = [y for y in lip_ys if not (inside(cover, lip_x, y, z_bond) and
                                       inside(cover, be.INNER_W / 2 + 0.3, y, z_bond))]
    assert not loose, f"lip not tied into the wall at y = {loose[:6]}"


def test_right_snap_tongues_are_free_to_flex(solids):
    _, cover = solids
    half = be.SIDE_SNAPS["half"]
    for y in be.SIDE_SNAPS["right_y"]:
        for side in (-1, 1):
            for z in (39.6, 41.0, ef.BASE_TOP_Z - 0.2):   # the free length, below the shoulder plate root
                assert not inside(cover, be.INNER_W / 2 - 0.5, y + side * (half + 0.3), z), (y, side, z)
    assert be.SNAP_FREE >= 0.5


# 2. DIN latch: gaps and strain


def test_latch_spring_stays_within_the_material_strain():
    assert be.latch_strain(be.LATCH["legs"]) <= be.LATCH_MAX_STRAIN


def test_strain_check_catches_the_old_latch():
    """The old 3-leg S spring: 0.8 mm legs over ~2.4 mm free length, 2 mm travel: ~28 % strain."""
    old = dict(be.LATCH, beam=0.8, travel=2.0, half_width=5.0, gap=0.4, reach=7.5, skin=1.5)
    assert be.latch_strain(3, old) > 0.2


def test_latch_travel_clears_the_hook():
    assert be.LATCH["travel"] >= be.HOOK_REACH + 0.3


def test_latch_gaps_do_not_fuse_in_a_powder_print(solids):
    base, _ = solids
    lt = be.LATCH
    assert lt["gap"] >= be.MIN_PRINT_GAP
    z = -be.BACK_DEPTH / 2
    for dx in (0.1, lt["gap"] - 0.1):
        assert not inside(base, lt["half_width"] + dx, be.rail_edges()[0] - 3.0, z)
    tab_x = (lt["half_width"] + lt["gap"] + lt["tab_half_width"]) / 2
    assert not inside(base, tab_x, -lt["gap"] / 2, z), "tab must stay MIN_PRINT_GAP below the case"
    hole_w, hole_h = lt["hole"]
    assert hole_w >= 3.0 and hole_h >= 1.6


def test_flexure_slots_inside_one_part_do_not_fuse():
    """Button C-slots and the UI snap-tongue slots are gaps inside the cover print."""
    assert be.BUTTON_TAB["slot"] >= be.MIN_PRINT_GAP
    assert be.SNAP["slot"] >= be.MIN_PRINT_GAP


# 3. Legend sizes and strokes

PIXEL = 0.02


def raster(path):
    """Filled path on a PIXEL grid (even-odd, so letter counters stay open)."""
    ext = path.get_extents()
    xs = np.arange(ext.x0 - 0.5, ext.x1 + 0.5, PIXEL)
    ys = np.arange(ext.y0 - 0.5, ext.y1 + 0.5, PIXEL)
    gx, gy = np.meshgrid(xs, ys)
    points = np.column_stack([gx.ravel(), gy.ravel()])
    ink = np.zeros(len(points), dtype=bool)
    for ring in path.to_polygons(closed_only=True):
        if len(ring) > 3:
            ink ^= fl.MplPath(ring).contains_points(points)
    return ink.reshape(gx.shape)


def opened(mask, radius):
    """Morphological opening with a disc: the ink a tool of that radius can fill."""
    r = round(radius / PIXEL)
    offsets = [(dy, dx) for dy in range(-r, r + 1) for dx in range(-r, r + 1) if dx * dx + dy * dy <= r * r]

    def shifted(m, dy, dx):
        out = np.zeros_like(m)
        out[max(dy, 0):m.shape[0] + min(dy, 0), max(dx, 0):m.shape[1] + min(dx, 0)] = \
            m[max(-dy, 0):m.shape[0] + min(-dy, 0), max(-dx, 0):m.shape[1] + min(-dx, 0)]
        return out

    eroded = np.ones_like(mask)
    for dy, dx in offsets:
        eroded &= shifted(mask, dy, dx)
    dilated = np.zeros_like(mask)
    for dy, dx in offsets:
        dilated |= shifted(eroded, dy, dx)
    return dilated & mask


def thin_fraction(path, stroke=fl.MIN_STROKE):
    """Share of the ink in strokes narrower than `stroke`, which a powder print smears."""
    mask = raster(path)
    return 1 - opened(mask, stroke / 2).sum() / mask.sum()


ALL_LABELS = fl.labels() + fl.side_labels()


def test_legend_is_big_and_deep_enough_for_a_powder_print():
    """The knx print had 0.85-2.6 mm letters 0.3 mm deep: unreadable."""
    assert le.INLAY_DEPTH >= 0.6
    assert all(lb.height >= fl.MIN_TEXT_H for lb in ALL_LABELS), [(lb.text, lb.height) for lb in ALL_LABELS]


@pytest.mark.parametrize("label", ALL_LABELS, ids=lambda lb: f"{lb.text}@{lb.x:.1f},{lb.y:.1f}")
def test_legend_strokes_are_wide_enough_for_a_powder_print(label):
    assert thin_fraction(label.path()) <= 0.2


def test_stroke_check_catches_the_old_small_text():
    assert thin_fraction(fl.Label("STATUS", 0, 0, 0.85).path()) > 0.5


def test_front_carries_no_connector_names_or_long_words():
    texts = {lb.text for lb in fl.labels()}
    assert texts == {"RST", "PG"}, texts


# 4. Connector names beside their connectors, really engraved


def _body(ref):
    return next(b for b in ef.part_boxes() if (b["board"], b["ref"]) == ("main", ref))


def test_pole_names_sit_beside_their_poles():
    side = fl.side_labels()
    bank_names = [lb for lb in side if fl.side_to_enc(lb.x, lb.y)[1] > ef.HIDDEN_H / 2]
    assert [lb.text for lb in bank_names] == ["5V", "24V", "mA", "10V", "IO1", "IO2", "IO3", "IO4", "GND", "GND"]
    for lb, z in zip(bank_names, be.sensor_pole_z()):
        assert abs(fl.side_to_enc(lb.x, lb.y)[0] - z) < 0.05, lb.text
    bank = [_body(r) for r in ef.SPEC["terminals"]["sensor_io"]["refs"]]
    y0 = min(b["y0"] for b in bank) - 10
    for lb in side:
        z, y = fl.side_to_enc(lb.x, lb.y)
        if y > ef.HIDDEN_H / 2:
            assert y > y0 and min(b["z0"] for b in bank) < z < max(b["z1"] for b in bank), lb.text
        else:
            ref = "J1" if any(abs(z - pz) < 3 for pz in be._pin_z_positions("J1").values()) or lb.text == "9-30V" \
                else "J4"
            body = _body(ref)
            assert body["z0"] < z < body["z1"] and y < body["y1"] + 10, (lb.text, ref)


def test_side_labels_clear_each_other_and_the_keepers():
    side = fl.side_labels()
    pairs = [(a.text, b.text) for i, a in enumerate(side) for b in side[i + 1:]
             if fl.overlaps(a.box(), b.box(), fl.LABEL_SPACING)]
    hits = [lb.text for lb in side for k in fl.side_keepouts() if fl.overlaps(lb.box(), k, 0.3)]
    assert not pairs and not hits, (pairs, hits)


def ink_points(label, n=10):
    mask = raster(label.path())
    ext = label.path().get_extents()
    ys, xs = np.nonzero(opened(mask, fl.MIN_STROKE / 2))
    pick = np.linspace(0, len(xs) - 1, n).astype(int)
    return [(ext.x0 - 0.5 + xs[i] * PIXEL, ext.y0 - 0.5 + ys[i] * PIXEL) for i in pick]


@pytest.mark.parametrize("label", fl.side_labels(), ids=lambda lb: f"{lb.text}@{lb.x:.1f},{lb.y:.1f}")
def test_side_names_are_engraved_into_solid_wall(solids, label):
    base, _ = solids
    depth = le.INLAY_DEPTH
    for u, v in ink_points(label):
        z, y = fl.side_to_enc(u, v)
        assert not inside(base, ef.WIDTH / 2 - depth / 2, y, z), f"{label.text} not engraved at {(y, z)}"
    u0, v0, u1, v1 = label.box()
    for i in range(5):
        for j in range(3):
            z, y = fl.side_to_enc(u0 + (u1 - u0) * i / 4, v0 + (v1 - v0) * j / 2)
            assert inside(base, ef.WIDTH / 2 - depth - 0.3, y, z), f"less than 0.3 mm of wall behind {label.text}"


# 5. Terminal releases reachable (a KF142R's top-face buttons faced the side wall)


def test_j4_screws_are_reachable_through_the_side(solids):
    """DG127R screws sit in the top face, which faces the right wall: a 2.5 mm blade
    must reach each one along a straight line from outside, through nothing printed."""
    for hole in be.screw_holes():
        assert hole["d"] >= 3.0
        for x in np.arange(hole["body_x1"] + 0.05, ef.WIDTH / 2 + 0.5, 0.25):
            for dy, dz in ((0, 0), (-1.2, 0), (1.2, 0), (0, -1.2), (0, 1.2)):
                assert not any(inside(s, x, hole["y"] + dy, hole["z"] + dz) for s in solids), (hole, round(x, 2))


def test_j4_screw_heads_stay_inside_the_wall():
    """Nothing of the 230 V terminal reaches the case side (a KF142R's levers stood 13.7 mm, out of it)."""
    assert _body("J4")["x1"] <= be.INNER_W / 2 - 0.5


def test_j1_push_buttons_open_in_the_bottom_face(solids):
    """WAGO 2086: buttons and wire entries in the wire-entry face, which the bottom-wall slot exposes."""
    body = _body("J1")
    for x in (body["x0"] + 0.5, (body["x0"] + body["x1"]) / 2, body["x1"] - 0.5):
        for z in (body["z0"] + 0.5, (body["z0"] + body["z1"]) / 2, body["z1"] - 0.5):
            assert not any(inside(s, x, be.WALL / 2, z) for s in solids), (x, z)


@pytest.mark.parametrize(("ref", "length", "depth"), [("J1", 7.7, 13.6), ("J4", 3 * 5.08, 8.1)])
def test_bottom_terminal_bodies_follow_the_datasheets(ref, length, depth):
    """WAGO 2086: L = (poles - 1) x 3.5 + 4.2; Degson DG127R: L = 3 x 5.08, depth 8.1 mm.
    The part box is courtyard + Fab outline: it holds the datasheet body, the WAGO's rear solder
    pads (behind the body) and at most 0.25 mm of courtyard margin along the pole row."""
    body = _body(ref)
    assert length <= body["z1"] - body["z0"] <= length + 0.25, ref
    assert body["y1"] - body["y0"] >= depth - 0.05, ref


@pytest.mark.parametrize("ref", ef.BOTTOM_TERMINAL_REFS)
def test_wire_entry_opening_fits_the_datasheet_body(ref):
    body = _body(ref)
    slot = next(s for s in be.terminal_slots() if s["ref"] == ref)
    assert slot["z0"] <= body["z0"] - 0.2 and body["z1"] + 0.2 <= slot["z1"], (slot, body)
    assert slot["z0"] >= body["z0"] - 0.35 and slot["z1"] <= body["z1"] + 0.35


# 6. Board supported in front, every quadrant


def test_board_front_rests_on_the_case_in_every_quadrant(solids):
    """The knx print had no support there: its tallest capacitor carried the board."""
    base, _ = solids
    slab = ef.board_slab("main")
    x = slab["x1"] + 0.15
    y_mid, z_mid = (slab["y0"] + slab["y1"]) / 2, (slab["z0"] + slab["z1"]) / 2
    quadrants = set()
    for y in np.arange(slab["y0"], slab["y1"], 0.25):
        for z in np.arange(slab["z0"], slab["z1"], 0.5):
            if inside(base, x, y, z):
                quadrants.add((y > y_mid, z > z_mid))
    assert len(quadrants) == 4, quadrants


def test_supports_hold_the_board_before_any_part_touches_the_case():
    assert be.BOARD_SUPPORT_GAP < be.PART_AIR


def test_posts_stand_in_part_free_columns():
    parts = [b for b in ef.part_boxes() if b["board"] == "main"]
    for y, z in be.front_posts():
        assert be._yz_clear(parts, y, z, be.POST_HALF), (y, z)


# 7. Cover side wall backed often enough


def test_cover_side_wall_is_backed_at_least_every_40_mm():
    """The knx cover's side wall dented between its end ribs; the end walls count as supports."""
    rows = sorted({round(y, 1) for y, _ in be.main_ribs()} | {be.WALL, ef.HIDDEN_H - be.WALL})
    assert max(b - a for a, b in pairwise(rows)) <= be.RIB["max_spacing"], rows


def test_cover_ribs_sweep_past_every_solder_tail():
    """The cover slides on along +x: each rib's (y, z) footprint must miss the tail recesses."""
    recesses = [p.val().BoundingBox() for p in be.tht_tail_recesses()]
    for y, z in be.main_ribs():
        for bb in recesses:
            assert (y + be.RIB["half_y"] <= bb.ymin or y - be.RIB["half_y"] >= bb.ymax or
                    z + be.RIB["half_z"] <= bb.zmin or z - be.RIB["half_z"] >= bb.zmax), (y, z)


# 8. Six clicks


def test_cover_clicks_on_at_both_ends_of_both_sides():
    snaps = be.SIDE_SNAPS
    assert len(snaps["right_y"]) >= 2 and len(snaps["left_z"]) >= 2
    right = sorted(snaps["right_y"])
    assert right[0] < ef.HIDDEN_H / 3 and right[-1] > 2 * ef.HIDDEN_H / 3
    left = sorted(z for pair in snaps["left_z"] for z in pair)
    assert left[0] < ef.BASE_TOP_Z / 3 and left[-1] > ef.BASE_TOP_Z * 2 / 3
    assert len(be.shoulder_snap_bodies()) == len(snaps["right_y"]) + 2 * len(snaps["left_z"]) == 6


def test_snap_tongues_keep_the_part_air_gap_to_every_part():
    for tongue in be.shoulder_snap_bodies():
        bb = tongue.val().BoundingBox()
        for p in ef.part_boxes():
            clear = (bb.xmax + be.PART_AIR <= p["x0"] or bb.xmin - be.PART_AIR >= p["x1"] or
                     bb.ymax + be.PART_AIR <= p["y0"] or bb.ymin - be.PART_AIR >= p["y1"] or
                     bb.zmax + be.PART_AIR <= p["z0"] or bb.zmin - be.PART_AIR >= p["z1"])
            assert clear, (p["ref"], bb.ymin, bb.zmin)


# Part bodies (datasheet Fab outlines) clear the printed parts


def test_every_main_part_body_clears_the_case(solids):
    """FDM_CLEAR around terminal bodies in their wall slots, PART_AIR elsewhere is checked
    by the fit tests; here every body grown by FDM_CLEAR - 0.05 must miss base and cover.
    The old J4 body (KF142R Fab outline) sat 0.05 mm above the floor."""
    c = be.FDM_CLEAR - 0.05
    for p in ef.part_boxes():
        if p["board"] != "main":
            continue
        probe = be.box(p["x0"] - c, p["x1"] + c, p["y0"] - c, p["y1"] + c, p["z0"] - c, p["z1"] + c).val()
        for part in solids:
            assert part.intersect(probe).Volume() < 1e-3, p["ref"]


# The release must ship the case this code builds


@pytest.mark.parametrize("released", ["enclosure", "box_enclosure"])
def test_released_case_files_match_a_fresh_export(tmp_path, released):
    """release.py copies mechanical/build (git-ignored); running it before the CAD build shipped
    the previous case (KF142R windows over J1 and J4) while every test here passed on the new one."""
    import build_box_enclosure as bx
    (be if released == "enclosure" else bx).export_parts(tmp_path)
    dst = REPO / "hardware/releases" / ef.VARIANT / released
    stls = sorted(tmp_path.glob("*.stl"))
    assert stls
    stale = [p.name for p in stls if (dst / p.name).read_bytes() != p.read_bytes()]
    assert not stale, f"{dst} differs from a fresh export: {stale}; run the CAD build, then release.py"
