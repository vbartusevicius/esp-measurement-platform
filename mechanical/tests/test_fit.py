"""Board-to-enclosure fit tests for the 1-DIN Universal Sensor Node."""

import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "mechanical/scripts"))
import enclosure_features as ef

SPEC = ef.SPEC
WALL = SPEC["enclosure"]["wall"]
MIN_GAP = SPEC["checks"]["component_to_cover_min_gap"]
MAIN_THICK = SPEC["boards"]["main"]["thickness"]
UI_TOP_Z = SPEC["front_ui"]["board_top_z"]
FRONT_INNER_Z = ef.TOTAL_D - WALL
THROUGH_FRONT = ef.THROUGH_FRONT


def heights(board):
    plan = yaml.safe_load((REPO / f"hardware/circuits/variants/{ef.VARIANT}/layout_{board}.yaml").read_text())
    return plan["heights"]


def part_height(board, ref):
    h = heights(board)
    return h.get(ref, h["default"])


def main_part_limits(comp, height):
    if comp["side"] == "back":
        return -ef.WIDTH / 2 + WALL, SPEC["boards"]["main"]["x"] - MAIN_THICK - height
    return SPEC["boards"]["main"]["x"] + height, ef.WIDTH / 2 - WALL


def main_height_violations(comps, height_of):
    bad = []
    for ref, comp in comps.items():
        top, limit = main_part_limits(comp, height_of(ref))
        if comp["side"] == "back" and limit < top + MIN_GAP - 1e-6:
            bad.append((ref, round(limit, 2), top))
        if comp["side"] == "front" and top > limit - MIN_GAP + 1e-6:
            bad.append((ref, round(top, 2), limit))
    return bad


def test_main_parts_have_clearance_to_walls():
    assert not main_height_violations(ef.components("main"), lambda r: part_height("main", r))


def test_main_height_check_catches_a_tall_part():
    comps = ef.components("main")
    assert main_height_violations(comps, lambda r: 30.0 if r == "U3" else part_height("main", r))


def test_ui_front_parts_stay_behind_front_wall():
    bad = [(ref, UI_TOP_Z + part_height("ui", ref)) for ref, c in ef.components("ui").items()
           if c["side"] == "front" and ref not in THROUGH_FRONT
           and UI_TOP_Z + part_height("ui", ref) > FRONT_INNER_Z - MIN_GAP + 1e-6]
    assert not bad


FLUSH_TOLERANCE = 0.25


def test_connector_faces_flush_with_top_and_bottom_faces():
    faces = ef.connector_faces()
    for ref in ef.TOP_TERMINAL_REFS:
        assert abs(faces[ref] - ef.HIDDEN_H) <= FLUSH_TOLERANCE, f"{ref}: {faces[ref]}"
    for ref in ef.BOTTOM_TERMINAL_REFS:
        assert abs(faces[ref]) <= FLUSH_TOLERANCE, f"{ref}: {faces[ref]}"
