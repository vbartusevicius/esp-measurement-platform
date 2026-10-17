"""JLCPCB assembly: every JLC part is what the circuit asks for and JLCPCB's
own footprint for it lands pin for pin on ours (hardware/scripts/jlc_parts.py).
The board checks use versioned supplier references; live stock/API gates are mocked."""

import io
import json
import sys
import urllib.error
from pathlib import Path

import pcbnew
import pytest
from board_variant import BOARDS, build_path, layout_path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "hardware/scripts"))
import jlc_parts as jp

SOT23 = [("1", -0.95, -1.0), ("2", 0.95, -1.0), ("3", 0.0, 1.0)]


def our_pads(pads, rotation=0, dx=10.0, dy=20.0, half=0.4):
    placed = []
    for n, x, y in pads:
        x, y = jp.rotate(x, y, rotation)
        placed.append(jp.Pad(n, dx + x - half, dy + y - half, dx + x + half, dy + y + half))
    return placed


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_fit_finds_the_rotation_and_centre(rotation):
    placement = jp.fit(our_pads(SOT23, rotation), SOT23, bottom=False)
    assert placement.rotation == rotation
    assert (placement.x, placement.y) == pytest.approx((10.0, 20.0))


def test_fit_rejects_swapped_pins():
    swapped = [("2", -0.95, -1.0), ("1", 0.95, -1.0), ("3", 0.0, 1.0)]
    assert jp.fit(our_pads(swapped), SOT23, bottom=False) is None


def test_fit_rejects_a_different_package():
    sot89 = [("1", -1.5, -2.0), ("2", 0.0, -2.0), ("3", 1.5, -2.0)]
    assert jp.fit(our_pads(SOT23), sot89, bottom=False) is None


def test_fit_mirrors_bottom_parts_about_their_x_axis():
    mirrored = [(n, x, -y) for n, x, y in SOT23]
    assert jp.fit(our_pads(mirrored), SOT23, bottom=True).rotation == 0
    assert jp.fit(our_pads(mirrored), SOT23, bottom=False) is None


def test_pad_map_allows_different_numbering_but_not_wrong_pins():
    """A 6 x 6 mm tact switch: contacts 1-2 and 3-4 run along the long side."""
    theirs = [("1", -4.5, 2.25), ("2", 4.5, 2.25), ("3", -4.5, -2.25), ("4", 4.5, -2.25)]
    ours = our_pads([("1", -4.5, 2.25), ("1", 4.5, 2.25), ("2", -4.5, -2.25), ("2", 4.5, -2.25)])
    pad_map = {"1": ["1"], "2": ["1"], "3": ["2"], "4": ["2"]}
    assert jp.fit(ours, theirs, bottom=False, pad_map=pad_map).rotation in (0, 180)
    across = our_pads([("1", -4.5, 2.25), ("2", 4.5, 2.25), ("1", -4.5, -2.25), ("2", 4.5, -2.25)])
    assert jp.fit(across, theirs, bottom=False, pad_map=pad_map) is None


@pytest.mark.parametrize("text,value", [("4k7", 4700), ("330R", 330), ("100n", 1e-7), ("10kΩ", 1e4),
                                        ("100nF", 1e-7), ("2.2uF", 2.2e-6), ("470u", 4.7e-4), ("27R", 27)])
def test_si_values(text, value):
    assert jp.si(text) == pytest.approx(value)


def record(model, **attributes):
    return {"componentModelEn": model,
            "attributes": [{"attribute_name_en": k.replace("_", " "), "attribute_value_name": v}
                           for k, v in attributes.items()]}


def test_value_check_catches_wrong_capacitance_rating_and_part():
    part = {"mpn": "CC0603KRX7R9BB104", "value": "100n 50V", "footprint": "Capacitor_SMD:C_0603_1608Metric"}
    assert not jp.value_problems(part, record("CC0603KRX7R9BB104", Capacitance="100nF", Voltage_Rating="50V"))
    assert jp.value_problems(part, record("CC0603KRX7R9BB104", Capacitance="10nF", Voltage_Rating="50V"))
    assert jp.value_problems(part, record("CC0603KRX7R9BB104", Capacitance="100nF", Voltage_Rating="25V"))
    assert jp.value_problems(part, record("CL10B104KB8NNNC", Capacitance="100nF", Voltage_Rating="50V"))


def test_board_checks_do_not_use_supplier_api_or_download_cache(monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("supplier API blocked")

    monkeypatch.setattr(jp, "fetch", unavailable)
    pcb = pcbnew.LoadBoard(str(layout_path("ui")))
    parts = json.loads(build_path("ui", "parts.json").read_text())
    checks = jp.check_board(pcb, parts)
    assert checks
    assert not [p for c in checks for p in c.problems]


def test_refresh_fetches_even_when_download_cache_exists(monkeypatch, tmp_path):
    cache = tmp_path / "record.json"
    cache.write_text('{"stale": true}')
    calls = []

    def response(request, **kwargs):
        calls.append(request.full_url)
        return io.BytesIO(b'{"fresh": true}')

    monkeypatch.setattr(jp.urllib.request, "urlopen", response)
    monkeypatch.setattr(jp.time, "sleep", lambda _: None)
    assert jp.fetch(jp.JLC_URL.format("C7484"), cache, refresh=True) == {"fresh": True}
    assert len(calls) == 1


def test_missing_reference_fails_without_network_fallback(monkeypatch):
    references = jp.load_reference()
    references.pop("C2890035")
    monkeypatch.setattr(jp, "load_reference", lambda: references)
    pcb = pcbnew.LoadBoard(str(layout_path("ui")))
    parts = json.loads(build_path("ui", "parts.json").read_text())
    checks = jp.check_board(pcb, parts)
    assert all(c.problems for c in checks if c.ref in ("D1", "D2", "D3"))


@pytest.mark.parametrize("blocked", [False, True])
def test_live_checks_reject_stock_shortages_and_api_failures(monkeypatch, blocked):
    references = jp.load_reference()
    calls = []

    def supplier(lcsc, *, refresh):
        assert refresh
        calls.append(lcsc)
        if blocked:
            raise urllib.error.HTTPError(jp.JLC_URL.format(lcsc), 403, "Forbidden", {}, None)
        data = references[lcsc]
        return {**data, "record": {**data["record"], "stockCount": 0}}

    monkeypatch.setattr(jp, "supplier_data", supplier)
    pcb = pcbnew.LoadBoard(str(layout_path("ui")))
    parts = json.loads(build_path("ui", "parts.json").read_text())
    checks = [c for c in jp.check_board(pcb, parts, live=True) if c.assembly == "jlc"]
    assert checks and all(c.problems for c in checks)
    if not blocked:
        assert len(calls) == len(set(calls))
        assert all(c.stock == 0 for c in checks)
    else:
        assert all("403" in c.problems[0] for c in checks)


@pytest.fixture(scope="module", params=BOARDS)
def board_checks(request):
    board = request.param
    pcb = pcbnew.LoadBoard(str(layout_path(board)))
    parts = json.loads(build_path(board, "parts.json").read_text())
    return parts, jp.check_board(pcb, parts)


def test_every_part_is_checked_and_lands_pin_for_pin(board_checks):
    """Hand-fitted parts too: against a JLCPCB footprint reference or the cited
    manufacturer pinout (hardware/product/pinouts.yaml)."""
    parts, checks = board_checks
    assert {c.ref for c in checks} == {p["ref"] for p in parts}
    assert not [f"{c.ref} {c.lcsc}: {p}" for c in checks for p in c.problems]


@pytest.mark.parametrize("ours,theirs,problem", [
    ({"1": "DOUT", "2": "VSS", "3": "DIN", "4": "VDD"}, {"1": "DIN", "2": "VDD", "3": "DOUT", "4": "GND"}, True),
    ({"1": "DIN", "2": "VDD", "3": "DOUT", "4": "GND"}, {"1": "DIN", "2": "VDD", "3": "DOUT", "4": "GND"}, False),
    ({"8": "D7", "14": "5V"}, {"8": "5V", "14": "D7"}, True),
    ({"1": "K", "2": "A"}, {"1": "C", "2": "A"}, False),
    ({"1": "Pin_1", "3": "~{CE}", "41": "EPAD"}, {"1": "1", "3": "CE#", "41": "EP"}, False),
])
def test_pin_name_check_catches_swapped_functions(ours, theirs, problem):
    """The SK6805-EC15 once used KiCad's SK6805 symbol (1 DOUT, 2 VSS, 3 DIN,
    4 VDD) on a footprint with the datasheet's numbers: the pads landed, the
    functions did not."""
    assert bool(jp.name_problems("D1", ours, theirs)) is problem


def test_pinout_check_catches_a_wrong_net():
    class FakePad:
        def __init__(self, number, net):
            self.number, self.net = number, net

        def GetNumber(self):
            return self.number

        def GetNetname(self):
            return self.net

    class FakeFootprint:
        def Pads(self):
            return [FakePad("1", "GND"), FakePad("2", "+3V3")]

    wanted = {"1": "+3V3", "2": "GND"}
    assert any("pin 1 carries 'GND'" in p for p in jp.net_problems(FakeFootprint(), wanted))
