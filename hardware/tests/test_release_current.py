"""The newest committed release matches the current boards and JLCPCB BOM/CPL exports."""

import filecmp
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "hardware/scripts"))
import release

LATEST = REPO / "hardware/releases" / release.RELEASE


@pytest.mark.parametrize("board", release.BOARDS)
def test_release_holds_the_stored_layout(board):
    for suffix in (".kicad_pcb", ".kicad_pro", ".kicad_dru"):
        stored = release.layout_path(board).with_suffix(suffix)
        assert filecmp.cmp(stored, LATEST / board / stored.name, shallow=False), f"{LATEST.name}/{board}/{stored.name}"


@pytest.mark.parametrize("board", release.BOARDS)
def test_release_assembly_files_match_a_fresh_export(board, tmp_path):
    release.assembly_files(board, tmp_path, release.assembly_checks(board, live=False))
    for name in (f"{board}_bom_jlc.csv", f"{board}_cpl_jlc.csv", f"{board}_hand_fit.csv"):
        assert (tmp_path / name).read_text() == (LATEST / board / name).read_text(), f"{LATEST.name}/{board}/{name}"
