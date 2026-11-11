"""Hand-assembly drawings (hardware/scripts/assembly_drawing.py): silkscreen references
are hidden wherever they would clash, so the release must show every part's place
and, only where it matters, its orientation the way the real part is marked."""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "hardware/scripts"))
import assembly_drawing as ad
from product_spec import all_boards, load_spec

BOARDS = tuple(all_boards(load_spec(), ad.VARIANT))


@pytest.mark.parametrize("board", BOARDS)
def test_every_sourced_part_is_drawn_on_its_own_side(board):
    parts = {p["ref"] for p in json.loads((ad.build(board) / "parts.json").read_text())}
    comps = {c["ref"]: c["side"] for c in json.loads((ad.build(board) / f"components_{board}.json").read_text())}
    placed = ad.placements(board)
    assert {e["ref"] for e in placed} == parts
    assert all(e["side"] == comps[e["ref"]] and e["value"] and e["bbox"]["x1"] > e["bbox"]["x0"] for e in placed)


@pytest.mark.parametrize("board", BOARDS)
def test_release_ships_the_assembly_drawing(board):
    pdf = REPO / "hardware/releases" / ad.VARIANT / board / f"{board}_assembly.pdf"
    assert pdf.exists() and pdf.read_bytes().startswith(b"%PDF")


@pytest.mark.parametrize("board", BOARDS)
def test_non_polar_parts_stay_unmarked(board):
    """A dot on every part hides the ones that matter."""
    for e in ad.placements(board):
        if e["footprint"].split(":")[-1].startswith(ad.NON_POLAR):
            assert e["mark"] is None, e["ref"]


@pytest.mark.parametrize("board", BOARDS)
def test_every_polarised_part_has_a_pin_1_pad(board):
    for e in ad.placements(board):
        if e["mark"] is not None:
            assert ad.pad_one(e) is not None, e["ref"]


@pytest.mark.parametrize(("footprint", "value", "mark"), [
    ("Diode_SMD:D_SMA", "SMAJ30A", "cathode"),       # unidirectional TVS: band = cathode
    ("Diode_SMD:D_SMA", "SMAJ40CA", None),           # bidirectional TVS: no polarity
    ("Diode_SMD:D_SOD-123", "B5819W", "cathode"),
    ("Capacitor_THT:CP_Radial_D5.0mm_P2.00mm", "100u", "plus"),
    ("Capacitor_SMD:C_0805_2012Metric", "100n 50V", None),
    ("Resistor_SMD:R_0805_2012Metric", "10k", None),
    ("Inductor_SMD:L_Sunlord_SWPA4020S", "22uH", None),
    ("Fuse:Fuse_1812_4532Metric", "1.1A", None),
    ("Button_Switch_SMD:SW_SPST_B3U-1000P", "B3U-1000P", None),
    ("Package_TO_SOT_SMD:SOT-23", "BAT54S", "pin1"),
    ("gateway_fp:LED_WS2812B-MINI-V3J", "WS2812B-MINI-V3J", "pin1"),
    ("LED_SMD:LED_0805_2012Metric", "red", "pin1"),
])
def test_polarity_follows_the_footprint_and_the_tvs_suffix(footprint, value, mark):
    assert ad.polarity(footprint, value) == mark
