"""Hand-assembly drawings: silkscreen references are hidden wherever they would
clash, so the release must show every part's place, reference and value elsewhere."""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "hardware/scripts"))
import assembly_drawing as ad
import release


@pytest.mark.parametrize("board", release.BOARDS)
def test_every_part_has_a_place_reference_and_value(board):
    parts = {p["ref"] for p in json.loads((ad.build(board) / "parts.json").read_text())}
    placed = ad.placements(board)
    assert {e["ref"] for e in placed} == parts
    assert all(e["value"] and e["bbox"]["x1"] > e["bbox"]["x0"] and e["bbox"]["y1"] > e["bbox"]["y0"]
               for e in placed)


@pytest.mark.parametrize("board", release.BOARDS)
def test_release_ships_the_assembly_drawing(board):
    pdf = REPO / "hardware/releases" / ad.VARIANT / board / f"{board}_assembly.pdf"
    assert pdf.exists() and pdf.read_bytes().startswith(b"%PDF")
