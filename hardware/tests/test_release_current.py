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


@pytest.mark.parametrize("board", release.BOARDS)
def test_release_generic_assembly_files_match_a_fresh_export(board, tmp_path):
    release.generic_assembly_files(board, tmp_path)
    for name in (f"{board}_bom.csv", f"{board}_cpl.csv"):
        assert (tmp_path / name).read_text() == (LATEST / board / name).read_text(), f"{LATEST.name}/{board}/{name}"


def _assembled(board):
    return {p["ref"]: p for p in release.parts(board) if p["assembly"] == "jlc"}


@pytest.mark.parametrize("board", release.BOARDS)
def test_odb_and_ipc2581_carry_every_assembled_part_number_and_leave_out_hand_fit_parts(board):
    import re
    import zipfile

    with zipfile.ZipFile(LATEST / board / f"{board}_odb.zip") as odb:
        components = "".join(odb.read(n).decode(errors="replace") for n in odb.namelist() if n.endswith("/components"))
    placed = dict(re.findall(r"^CMP \d+ \S+ \S+ \S+ \S+ (\S+) .*?\nPRP MPN '([^']*)'", components, re.M | re.S))
    hand = {p["ref"] for p in release.parts(board) if p["assembly"] == "hand"}
    for ref, part in _assembled(board).items():
        assert placed.get(ref) == part["mpn"], f"{board} ODB++ {ref}"
    # hand-fit parts stay in the geometry with ODB++'s ".no_pop" attribute; assembled ones without it
    no_pop = {}
    for layer in re.split(r"(?=^UNITS=)", components, flags=re.M):
        names = dict(re.findall(r"^@(\d+) (\S+)", layer, re.M))
        for ref, attrs in re.findall(r"^CMP \d+ \S+ \S+ \S+ \S+ (\S+) \S+ ;(\S+)", layer, re.M):
            ids = {a.split("=")[0] for a in attrs.split(",")}   # "0=2,1": attribute 0 = option 2, attribute 1 set
            no_pop[ref] = any(names.get(i) == ".no_pop" for i in ids)
    assert {ref for ref, flag in no_pop.items() if flag} == hand, f"{board}: .no_pop set on {no_pop}"

    with zipfile.ZipFile(LATEST / board / f"{board}_ipc2581.zip") as ipc:
        xml = ipc.read(ipc.namelist()[0]).decode(errors="replace")
    for part in _assembled(board).values():
        assert part["mpn"] in xml, f"{board} IPC-2581 {part['mpn']}"


@pytest.mark.parametrize("board", release.BOARDS)
def test_generic_placement_lists_every_assembled_part_in_gerber_coordinates(board):
    import csv

    import pcbnew

    rows = {r["Designator"]: r for r in csv.DictReader(open(LATEST / board / f"{board}_cpl.csv"))}
    assert set(rows) == set(_assembled(board)), board
    pcb = pcbnew.LoadBoard(str(release.layout_path(board)))
    for ref, r in rows.items():
        fp = pcb.FindFootprintByReference(ref)
        # KiCad's Gerbers keep the board's absolute origin with Y pointing up
        assert float(r["Mid X"]) == pytest.approx(fp.GetPosition().x / 1e6, abs=0.002), ref
        assert float(r["Mid Y"]) == pytest.approx(-fp.GetPosition().y / 1e6, abs=0.002), ref
        assert r["Layer"] == ("Bottom" if fp.IsFlipped() else "Top"), ref
