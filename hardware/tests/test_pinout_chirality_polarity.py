"""Test 1 — Independent Datasheet Pinout, Chirality & Polarity Verification Gate.

Loads ONLY the final routed `.kicad_pcb` (via `pcbnew`) and the exported
production BOM CSV (`hardware/releases/v1/<board>/<board>_bom.csv`) — ZERO
imports from `hardware/circuits/`, `skidl`, `gen_circuits.py` or `parts.json`.

Verifies:
  1. Footprint chirality (`F.Cu` and `B.Cu`) via signed shoelace area in each
     component's mounting-face top view, catching footprints accidentally
     mirrored by `Flip()` on `B.Cu` or drawn upside-down.
  2. Standalone datasheet-audited MPN pin-role & passive-divider topology checks
     for every IC, transistor, regulator, comparator, optosensor, relay, LED,
     MCU module and connector across `main`, `ui` and `reader`.
  3. Non-swapped bus lines (I2C `SDA`/`SCL` end-to-end across FFC, WS2812B LED
     chain), zero shorted/open 2-pin passives, and correct DC `Anode` vs
     `Cathode` bias + physical silkscreen cathode-mark proximity on every diode,
     Zener, LED and TVS.
"""

from __future__ import annotations

import csv
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pcbnew
import pytest

REPO = Path(__file__).resolve().parents[2]
BOARDS = ("main", "ui", "reader")
FORBIDDEN_MODULES = ("skidl", "gen_circuits", "common", "product_spec", "blocks", "variants")


@dataclass(frozen=True)
class BomEntry:
    ref: str
    value: str
    manufacturer: str
    mpn: str
    lcsc: str
    package: str
    mount_type: str
    place: str


def load_bom(board: str) -> dict[str, BomEntry]:
    bom_path = REPO / "hardware/releases/v1" / board / f"{board}_bom.csv"
    entries: dict[str, BomEntry] = {}
    with open(bom_path, newline="") as f:
        for row in csv.DictReader(f):
            for ref in row["Designator"].split(","):
                ref = ref.strip()
                entries[ref] = BomEntry(
                    ref=ref,
                    value=row["Value"].strip(),
                    manufacturer=row["Manufacturer"].strip(),
                    mpn=row["MPN"].strip(),
                    lcsc=row["LCSC"].strip(),
                    package=row["Package"].strip(),
                    mount_type=row["Type"].strip(),
                    place=row["Place"].strip(),
                )
    return entries


def load_pcb(board: str) -> pcbnew.BOARD:
    path = REPO / "hardware/layout/v1" / board / f"{board}.kicad_pcb"
    return pcbnew.LoadBoard(str(path))


def parse_ohms(val: str) -> float | None:
    token = val.strip().split()[0]
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([RkmM]?)(\d*)", token)
    if not m:
        return None
    whole, mult, frac = m.groups()
    num = float(f"{whole}.{frac}" if frac else whole)
    scale = {"": 1.0, "R": 1.0, "k": 1e3, "M": 1e6, "m": 1e-3}[mult]
    return num * scale


def parse_farads(val: str) -> float | None:
    token = val.strip().split()[0]
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([pnuµ]?)(\d*)F?", token)
    if not m or not m.group(2):
        return None
    whole, mult, frac = m.groups()
    num = float(f"{whole}.{frac}" if frac else whole)
    scale = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6}[mult]
    return num * scale


def mounting_face_xy(fp: pcbnew.FOOTPRINT, pt: pcbnew.VECTOR2I) -> tuple[float, float]:
    """Coordinates in component mounting-face top view (+x right, +y up):
    for `F.Cu` this is `(+x_board, +y_up)`; for `B.Cu` flipped parts viewed looking
    down onto `B.Cu` (flipped about Y axis) this is `(-x_board, +y_up)`."""
    sign_x = -1.0 if fp.IsFlipped() else 1.0
    return sign_x * pcbnew.ToMM(pt.x), -pcbnew.ToMM(pt.y)


def pad_centers_mounting_view(fp: pcbnew.FOOTPRINT) -> dict[str, tuple[float, float]]:
    pts: dict[str, list[tuple[float, float]]] = {}
    for pad in fp.Pads():
        num = pad.GetNumber().strip()
        if not num:
            continue
        pts.setdefault(num, []).append(mounting_face_xy(fp, pad.GetPosition()))
    return {
        num: (sum(p[0] for p in plist) / len(plist), sum(p[1] for p in plist) / len(plist))
        for num, plist in pts.items()
    }


def pad_nets(fp: pcbnew.FOOTPRINT) -> dict[str, str]:
    out: dict[str, str] = {}
    for pad in fp.Pads():
        num = pad.GetNumber().strip()
        if not num:
            continue
        net = pad.GetNetname()
        if num in out and out[num] and net and out[num] != net:
            raise AssertionError(f"{fp.GetReference()} split pad {num} has conflicting nets: {out[num]} vs {net}")
        out[num] = net or out.get(num, "")
    return out


def signed_shoelace_area(poly: list[tuple[float, float]]) -> float:
    n = len(poly)
    if n < 3:
        raise ValueError("shoelace requires >= 3 vertices")
    area2 = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        area2 += x1 * y2 - x2 * y1
    return 0.5 * area2


# Standalone datasheet-audited chirality specification keyed by MPN:
# `(ordered_pin_loop, expected_sign, min_abs_area_mm2)`
# +1 = JEDEC counter-clockwise top-view winding; -1 = datasheet clockwise winding.
CHIRALITY_BY_MPN: dict[str, tuple[tuple[str, ...], int, float]] = {
    # SCT2601TVBR (TSOT-23-6, JEDEC CCW 1..6)
    "SCT2601TVBR": (("1", "2", "3", "4", "5", "6"), +1, 2.0),
    # SN74AHCT1G125DBVR (SOT-23-5, JEDEC CCW 1..5 — mounted on B.Cu of ui!)
    "SN74AHCT1G125DBVR": (("1", "2", "3", "4", "5"), +1, 2.0),
    # LMV331IDBVR (SOT-23-5, JEDEC CCW 1..5)
    "LMV331IDBVR": (("1", "2", "3", "4", "5"), +1, 2.0),
    # MMBT3904 (SOT-23, JEDEC CCW 1=B, 2=E, 3=C)
    "MMBT3904(RANGE:100-300)": (("1", "2", "3"), +1, 1.0),
    # BAT54S,215 (SOT-23, JEDEC CCW 1=A1, 2=K2, 3=COM)
    "BAT54S,215": (("1", "2", "3"), +1, 1.0),
    # Seeed XIAO ESP32C6 (DIP-14 2.54 mm, CCW 1..14)
    "102010636": (tuple(str(i) for i in range(1, 15)), +1, 150.0),
    # Omron G6B-2114P-US DC5 (DIP-like 1, 3, 4, 5, 6, 8 CCW)
    "G6B-2114P-US DC5": (("1", "3", "4", "5", "6", "8"), +1, 80.0),
    # Worldsemi WS2812B-MINI-V3J (datasheet p.2: 1=VDD TL, 2=DOUT TR, 3=GND BR, 4=DIN BL -> CW)
    "WS2812B-MINI-V3J": (("1", "2", "3", "4"), -1, 5.0),
    # Vishay TCRT5000 (CNY70 pin numbering: 1=A TR, 2=K BR, 4=E BL, 3=C TL -> CW around 1-2-4-3; mounted on B.Cu!)
    "TCRT5000": (("1", "2", "4", "3"), -1, 10.0),
    # Bourns TC33X-2-103E trimmer (top view: 1 BL, 2 apex top, 3 BR -> CW 1-2-3)
    "TC33X-2-103E": (("1", "2", "3"), -1, 2.0),
}

# Nominal DC operating voltages (V) on named rails/nodes for independent diode bias checks
NOMINAL_DC_VOLTS: dict[str, float] = {
    "GND": 0.0,
    "VIN_RAW": 24.0,
    "VIN_FUSED": 24.0,
    "+24V_LOOP": 23.6,
    "BUCK5_SW": 5.05,
    "+5V": 5.05,
    "+5V_XIAO": 4.65,
    "+3V3": 3.30,
    "+5V_IN": 5.05,
    "+5V_S": 4.75,
    "RELAY_COIL_N": 0.2,   # energized low-side collector (5.05 V when off; <= +5V always, flyback K=+5V, A=COIL_N)
    "MA_MCU": 1.44,
    "V0_10_MCU": 1.56,
    "IO1_MCU": 3.30,
    "IO2_MCU": 3.30,
    "IO3_MCU": 3.30,
    "IO4_MCU": 3.30,
    "LED_A": 3.80,
    "CMP_OUT": 0.15,
}


@pytest.fixture(scope="module")
def loaded_boards():
    data = {}
    for b in BOARDS:
        pcb = load_pcb(b)
        bom = load_bom(b)
        fps = {fp.GetReference(): fp for fp in pcb.Footprints()}
        # Build net -> list of (ref, pin_num, mpn, value)
        net_index: dict[str, list[tuple[str, str, str, str]]] = {}
        for ref, fp in fps.items():
            entry = bom[ref]
            for num, net in pad_nets(fp).items():
                if net:
                    net_index.setdefault(net, []).append((ref, num, entry.mpn, entry.value))
        data[b] = (pcb, bom, fps, net_index)
    return data


def test_zero_circuit_generator_imports():
    """Verify strict independence: this test file imports zero modules from the
    circuit generator, layout scripts or `board_variant`, and `skidl`/`gen_circuits`
    are never loaded."""
    import ast

    tree = ast.parse(Path(__file__).read_text())
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    forbidden = set(FORBIDDEN_MODULES) | {"board_variant", "layout", "placer", "release", "jlc_parts"}
    assert not (imported & forbidden), f"Forbidden imports in {Path(__file__).name}: {imported & forbidden}"
    leaked = [m for m in sys.modules if m in ("skidl", "gen_circuits", "common", "blocks", "variants")]
    assert not leaked, f"Forbidden generator modules loaded: {leaked}"


def test_shoelace_chirality_catches_accidental_mirror():
    """Self-test: mirroring a SOT-23-5 footprint flips signed shoelace area negative."""
    sot23_5_ccw = [(-0.95, -1.1), (0.0, -1.1), (0.95, -1.1), (0.95, 1.1), (-0.95, 1.1)]
    mirrored = [(-x, y) for x, y in sot23_5_ccw]
    assert signed_shoelace_area(sot23_5_ccw) > 2.0
    assert signed_shoelace_area(mirrored) < -2.0


@pytest.mark.parametrize("board", BOARDS)
def test_bom_and_pcb_designators_match_one_to_one(loaded_boards, board):
    _pcb, bom, fps, _nets = loaded_boards[board]
    assert set(fps) == set(bom), f"{board}: PCB vs BOM designator mismatch: {set(fps) ^ set(bom)}"


@pytest.mark.parametrize("board", BOARDS)
def test_footprint_chirality_f_cu_and_b_cu(loaded_boards, board):
    """Every multi-pin IC, transistor, sensor, relay, LED and trimmer has the exact
    datasheet pin-winding chirality in its mounting-face view (`F.Cu` and `B.Cu`)."""
    _pcb, bom, fps, _nets = loaded_boards[board]
    checked = 0
    for ref, fp in sorted(fps.items()):
        mpn = bom[ref].mpn
        if mpn not in CHIRALITY_BY_MPN:
            continue
        pin_order, expected_sign, min_area = CHIRALITY_BY_MPN[mpn]
        centers = pad_centers_mounting_view(fp)
        missing = [p for p in pin_order if p not in centers]
        assert not missing, f"{board}:{ref} ({mpn}) missing expected pins {missing}"
        area = signed_shoelace_area([centers[p] for p in pin_order])
        side = "B.Cu" if fp.IsFlipped() else "F.Cu"
        assert area * expected_sign >= min_area, (
            f"{board}:{ref} ({mpn} on {side}) failed chirality check: "
            f"signed area={area:.3f} mm^2, expected sign={expected_sign:+d} (>= {min_area} mm^2)"
        )
        checked += 1
    assert checked > 0


@pytest.mark.parametrize("board", BOARDS)
def test_linear_connector_pin_monotonicity(loaded_boards, board):
    """Every linear connector (FFC, OLED hotbar, terminal blocks) steps monotonically
    from pin 1..N at constant pitch without transposed pins on both F.Cu and B.Cu."""
    _pcb, bom, fps, _nets = loaded_boards[board]
    expected_pitches = {
        "FPC-05F-8PH20": (8, 0.50),
        "QG-6428TSWCG02": (14, 0.62),
        "2086-1202/700-000/997-604": (2, 3.50),
        "2086-1203/700-000/997-605": (3, 3.50),
        "2086-1204/700-000/997-605": (4, 3.50),
        "DG127R-5.08-03P-14-00A(H)": (3, 5.08),
        "2059-303/998-403": (3, 3.00),
    }
    for ref, fp in sorted(fps.items()):
        mpn = bom[ref].mpn
        if mpn not in expected_pitches:
            continue
        n_pins, pitch = expected_pitches[mpn]
        centers = pad_centers_mounting_view(fp)
        pts = [centers[str(i)] for i in range(1, n_pins + 1)]
        dx0 = pts[1][0] - pts[0][0]
        dy0 = pts[1][1] - pts[0][1]
        step0 = math.hypot(dx0, dy0)
        assert step0 == pytest.approx(pitch, abs=0.03), f"{board}:{ref} ({mpn}) pitch={step0:.3f} != {pitch}"
        for i in range(1, n_pins - 1):
            dxi = pts[i + 1][0] - pts[i][0]
            dyi = pts[i + 1][1] - pts[i][1]
            assert dxi == pytest.approx(dx0, abs=0.03) and dyi == pytest.approx(dy0, abs=0.03), (
                f"{board}:{ref} ({mpn}) non-monotonic pin step at pin {i + 1}"
            )


def _other_pin_net(fp: pcbnew.FOOTPRINT, used_pin: str) -> str:
    nets = pad_nets(fp)
    other = [n for p, n in nets.items() if p != used_pin]
    assert len(other) == 1
    return other[0]


def test_independent_mpn_pin_roles_main(loaded_boards):
    """Verify every IC, transistor, regulator, module, relay and connector pin role on `main`
    against standalone datasheet rules."""
    _pcb, bom, fps, net_index = loaded_boards["main"]

    # 1. SCT2601TVBR (U1, TSOT-23-6): 1=BST, 2=GND, 3=FB, 4=EN, 5=VIN, 6=SW
    sct_refs = [r for r, e in bom.items() if e.mpn == "SCT2601TVBR"]
    assert sct_refs == ["U1"]
    u1_nets = pad_nets(fps["U1"])
    assert u1_nets["2"] == "GND"
    assert u1_nets["5"] == "+24V_LOOP"
    assert u1_nets["6"] == "BUCK5_SW"
    # Pin 1 (BST) must connect via 100nF bootstrap capacitor to BUCK5_SW (pin 6)
    bst_peers = [(r, p) for r, p, _, _ in net_index[u1_nets["1"]] if r != "U1"]
    assert len(bst_peers) == 1
    bst_cap_ref, bst_cap_pin = bst_peers[0]
    assert parse_farads(bom[bst_cap_ref].value) == pytest.approx(100e-9)
    assert _other_pin_net(fps[bst_cap_ref], bst_cap_pin) == "BUCK5_SW"
    # Pin 3 (FB, Vref=0.765 V) must have resistor divider to +5V and GND yielding 5.05 V +-2%
    fb_res = [(r, _other_pin_net(fps[r], p)) for r, p, _, _ in net_index[u1_nets["3"]] if r != "U1"]
    fb_by_rail = {rail: parse_ohms(bom[r].value) for r, rail in fb_res}
    assert set(fb_by_rail) == {"+5V", "GND"}
    v_out = 0.765 * (1.0 + fb_by_rail["+5V"] / fb_by_rail["GND"])
    assert 4.95 <= v_out <= 5.15, f"SCT2601 FB divider yields {v_out:.3f} V"
    # Pin 4 (EN, V_EN_rising=1.223 V) must have UVLO divider to +24V_LOOP and GND turning on ~7-8 V
    en_res = [(r, _other_pin_net(fps[r], p)) for r, p, _, _ in net_index[u1_nets["4"]] if r != "U1"]
    en_by_rail = {rail: parse_ohms(bom[r].value) for r, rail in en_res}
    assert set(en_by_rail) == {"+24V_LOOP", "GND"}
    v_uvlo = 1.223 * (1.0 + en_by_rail["+24V_LOOP"] / en_by_rail["GND"])
    assert 6.5 <= v_uvlo <= 8.5, f"SCT2601 UVLO divider yields {v_uvlo:.2f} V"

    # 2. Inductor FNR4020S220MT (L1): bridges BUCK5_SW and +5V
    assert set(pad_nets(fps["L1"]).values()) == {"BUCK5_SW", "+5V"}

    # 3. Seeed XIAO ESP32C6 (102010636, U3): exact 14-pin assignment
    expected_xiao = {
        "1": "V0_10_MCU", "2": "MA_MCU", "3": "BTN_LADDER", "4": "LED_DATA",
        "5": "I2C_SDA", "6": "I2C_SCL", "7": "IO2_MCU", "8": "IO1_MCU",
        "9": "RELAY_MCU", "10": "IO3_MCU", "11": "IO4_MCU",
        "12": "+3V3", "13": "GND", "14": "+5V_XIAO",
    }
    assert pad_nets(fps["U3"]) == expected_xiao

    # 4. MMBT3904 NPN transistor (Q1, SOT-23): 1=B, 2=E (GND), 3=C (RELAY_COIL_N)
    q1_nets = pad_nets(fps["Q1"])
    assert q1_nets == {"1": "RELAY_BASE", "2": "GND", "3": "RELAY_COIL_N"}

    # 5. Omron G6B-2114P-US DC5 relay (K1): 1/8 coil, 3&6 joined COM, 4=NO, 5=NC
    k1_nets = pad_nets(fps["K1"])
    assert k1_nets == {
        "1": "RELAY_COIL_N", "8": "+5V",
        "3": "RELAY_COM", "6": "RELAY_COM",
        "4": "RELAY_NO", "5": "RELAY_NC",
    }

    # 6. BAT54S dual series Schottky clamps (D3..D6, D10, D11): 1=A1(GND), 2=K2(+3V3), 3=COM(signal)
    bat_refs = sorted(r for r, e in bom.items() if e.mpn == "BAT54S,215")
    assert bat_refs == ["D10", "D11", "D3", "D4", "D5", "D6"]
    clamped_signals = set()
    for ref in bat_refs:
        bn = pad_nets(fps[ref])
        assert bn["1"] == "GND", f"{ref} pin 1 (Anode) must be GND, got {bn['1']}"
        assert bn["2"] == "+3V3", f"{ref} pin 2 (Cathode) must be +3V3, got {bn['2']}"
        assert bn["3"].endswith("_MCU"), f"{ref} pin 3 (Common) must be an MCU signal, got {bn['3']}"
        clamped_signals.add(bn["3"])
    assert clamped_signals == {"MA_MCU", "V0_10_MCU", "IO1_MCU", "IO2_MCU", "IO3_MCU", "IO4_MCU"}

    # 7. External terminals on `main`
    assert pad_nets(fps["J1"]) == {"1": "GND", "2": "VIN_RAW"}
    assert pad_nets(fps["J4"]) == {"1": "RELAY_COM", "2": "RELAY_NO", "3": "RELAY_NC"}
    assert pad_nets(fps["J2"]) == {"1": "+5V", "2": "+24V_LOOP", "3": "MA_TERM", "4": "V0_10_TERM"}
    assert pad_nets(fps["J5"]) == {"1": "IO1_TERM", "2": "IO2_TERM", "3": "IO3_TERM"}
    assert pad_nets(fps["J6"]) == {"1": "IO4_TERM", "2": "GND", "3": "GND"}


def test_independent_mpn_pin_roles_ui(loaded_boards):
    """Verify buffer IC, addressable RGB LEDs, SSD1312 OLED hotbar and switches on `ui`."""
    _pcb, bom, fps, net_index = loaded_boards["ui"]

    # 1. SN74AHCT1G125DBVR (U1, SOT-23-5): 1=/OE (GND active), 2=A (LED_DATA), 3=GND, 4=Y, 5=VCC (+5V)
    u1_nets = pad_nets(fps["U1"])
    assert u1_nets["1"] == "GND", "74AHCT1G125 /OE must be tied low (GND) to enable output"
    assert u1_nets["2"] == "LED_DATA"
    assert u1_nets["3"] == "GND"
    assert u1_nets["5"] == "+5V"
    # Pin 4 (Y) drives 330R series resistor to D1 pin 4 (DIN)
    y_peers = [(r, p) for r, p, _, _ in net_index[u1_nets["4"]] if r != "U1"]
    assert len(y_peers) == 1
    r_ser_ref, r_ser_pin = y_peers[0]
    assert parse_ohms(bom[r_ser_ref].value) == pytest.approx(330.0)
    din_first = _other_pin_net(fps[r_ser_ref], r_ser_pin)

    # 2. WS2812B-MINI-V3J LEDs (D1 -> D2 -> D3): 1=VDD(+5V), 2=DOUT, 3=GND, 4=DIN
    d1, d2, d3 = pad_nets(fps["D1"]), pad_nets(fps["D2"]), pad_nets(fps["D3"])
    for ref, dn in (("D1", d1), ("D2", d2), ("D3", d3)):
        assert dn["1"] == "+5V", f"{ref} pin 1 (VDD) != +5V"
        assert dn["3"] == "GND", f"{ref} pin 3 (GND) != GND"
    assert d1["4"] == din_first
    assert d1["2"] == d2["4"] and d1["2"] != ""
    assert d2["2"] == d3["4"] and d2["2"] != ""
    assert d3["2"] == "", "Last WS2812B DOUT must remain unconnected"

    # 3. QG-6428TSWCG02 14-pin SSD1312 OLED hotbar (J2)
    j2 = pad_nets(fps["J2"])
    assert j2["5"] == "+3V3" and j2["8"] == "+3V3"
    assert j2["6"] == ""
    assert j2["7"] == "GND"
    assert j2["10"] == "I2C_SCL" and j2["11"] == "I2C_SDA"
    # Flying caps across (1:C2P, 2:C2N) and (3:C1P, 4:C1N): each pair connected by 1uF cap
    for p_pos, p_neg in (("1", "2"), ("3", "4")):
        peers = [r for r, _, _, _ in net_index[j2[p_pos]] if r != "J2"]
        assert len(peers) == 1 and parse_farads(bom[peers[0]].value) == pytest.approx(1e-6)
        assert set(pad_nets(fps[peers[0]]).values()) == {j2[p_pos], j2[p_neg]}
    # Pin 12 (IREF): 390k resistor to GND
    iref_peers = [(r, p) for r, p, _, _ in net_index[j2["12"]] if r != "J2"]
    assert len(iref_peers) == 1
    assert parse_ohms(bom[iref_peers[0][0]].value) == pytest.approx(390e3)
    assert _other_pin_net(fps[iref_peers[0][0]], iref_peers[0][1]) == "GND"


def test_independent_mpn_pin_roles_reader(loaded_boards):
    """Verify LMV331 comparator (non-swapped IN+/IN- hysteresis!), TCRT5000, trimmer and terminal on `reader`."""
    _pcb, bom, fps, net_index = loaded_boards["reader"]

    # 1. LMV331IDBVR (U2, SOT-23-5): 1=IN+, 2=GND(V-), 3=IN-, 4=OUT, 5=VCC+
    u2 = pad_nets(fps["U2"])
    assert u2 == {
        "1": "SENSE_IN",
        "2": "GND",
        "3": "THRESHOLD",
        "4": "CMP_OUT",
        "5": "+5V_S",
    }
    # Prove positive (not negative!) feedback hysteresis: 390k bridges CMP_OUT (pin 4) to IN+ (pin 1), NOT IN- (pin 3)!
    in_plus_res = {parse_ohms(bom[r].value): _other_pin_net(fps[r], p)
                   for r, p, _, _ in net_index[u2["1"]] if r.startswith("R")}
    assert in_plus_res == {10e3: "SENSE", 390e3: "CMP_OUT"}

    # 2. Vishay TCRT5000 (U1, CNY70 numbering): 1=A(IR_A), 2=K(GND), 3=C(+5V_S), 4=E(SENSE)
    assert pad_nets(fps["U1"]) == {"1": "IR_A", "2": "GND", "3": "+5V_S", "4": "SENSE"}

    # 3. Bourns TC33X-2-103E trimmer (RV1): 1=+5V_S, 2=THRESHOLD (wiper), 3=GND
    rv1 = pad_nets(fps["RV1"])
    assert rv1["2"] == "THRESHOLD"
    assert {rv1["1"], rv1["3"]} == {"+5V_S", "GND"}

    # 4. WAGO 2059-303 terminal (J1): 1=+5V_IN, 2=GND, 3=PULSE
    assert pad_nets(fps["J1"]) == {"1": "+5V_IN", "2": "GND", "3": "PULSE"}


def test_non_swapped_bus_lines_and_interconnects(loaded_boards):
    """Assert non-swapped I2C SDA/SCL (+ pull-ups) and 8-pin FFC pin parity between `main:J3` and `ui:J1`."""
    _, main_bom, main_fps, main_nets = loaded_boards["main"]
    _, _ui_bom, ui_fps, _ui_nets = loaded_boards["ui"]

    j3_main = {k: v for k, v in pad_nets(main_fps["J3"]).items() if int(k) <= 8}
    j1_ui = {k: v for k, v in pad_nets(ui_fps["J1"]).items() if int(k) <= 8}
    expected_ffc = {
        "1": "+3V3", "2": "GND", "3": "BTN_LADDER", "4": "LED_DATA",
        "5": "+5V", "6": "I2C_SDA", "7": "I2C_SCL", "8": "GND",
    }
    assert j3_main == expected_ffc
    assert j1_ui == expected_ffc

    # Verify both I2C_SDA and I2C_SCL have 4.7k pull-ups to +3V3 on `main` and are not shorted together
    for bus_net in ("I2C_SDA", "I2C_SCL"):
        pullups = [
            r for r, p, _, _ in main_nets[bus_net]
            if r.startswith("R") and _other_pin_net(main_fps[r], p) == "+3V3"
            and parse_ohms(main_bom[r].value) == pytest.approx(4700.0)
        ]
        assert len(pullups) == 1, f"{bus_net} must have exactly one 4.7k pull-up to +3V3, found {pullups}"


@pytest.mark.parametrize("board", BOARDS)
def test_zero_shorted_or_open_two_pin_passives(loaded_boards, board):
    """Every 2-pin resistor, capacitor, inductor and polyfuse must connect two distinct non-empty nets."""
    _pcb, _bom, fps, _nets = loaded_boards[board]
    checked = 0
    for ref, fp in sorted(fps.items()):
        if not (ref.startswith(("R", "C", "L", "F")) and not ref.startswith("RV")):
            continue
        nets = pad_nets(fp)
        assert set(nets) == {"1", "2"}, f"{board}:{ref} unexpected pad numbers {sorted(nets)}"
        n1, n2 = nets["1"], nets["2"]
        assert n1 and n2, f"{board}:{ref} has open/unconnected pad: {nets}"
        assert n1 != n2, f"{board}:{ref} is shorted across single net {n1!r}"
        checked += 1
    assert checked > 0


def _silk_mark_centroid_board_mm(fp: pcbnew.FOOTPRINT) -> tuple[float, float]:
    """Weighted centroid of graphical SilkS lines/arcs/polygons on a 2-pin diode/LED footprint.
    In KiCad's standard diode/LED footprints, the cathode U-bracket + end bar shifts the SilkS
    centroid strictly toward the Cathode pad."""
    silk_layer = pcbnew.B_SilkS if fp.IsFlipped() else pcbnew.F_SilkS
    num_x, num_y, total_w = 0.0, 0.0, 0.0
    for gi in fp.GraphicalItems():
        if gi.Type() != pcbnew.PCB_SHAPE_T or gi.GetLayer() != silk_layer:
            continue
        bb = gi.GetBoundingBox()
        cx = pcbnew.ToMM(bb.GetCenter().x)
        cy = -pcbnew.ToMM(bb.GetCenter().y)
        w = max(0.2, pcbnew.ToMM(bb.GetWidth()) + pcbnew.ToMM(bb.GetHeight()))
        num_x += cx * w
        num_y += cy * w
        total_w += w
    assert total_w > 0, f"{fp.GetReference()} has no SilkS polarity marking"
    return num_x / total_w, num_y / total_w


@pytest.mark.parametrize("board", BOARDS)
def test_diode_dc_bias_and_silkscreen_cathode_proximity(loaded_boards, board):
    """Verify DC Anode vs Cathode bias AND physical silkscreen cathode-mark proximity
    on every 2-pin Schottky, Zener, TVS and indicator LED across all boards."""
    _pcb, bom, fps, _nets = loaded_boards[board]
    forward_Conducting = {("main", "D2"), ("main", "D12"), ("reader", "D1"), ("reader", "D2")}
    reverse_clamping = {("main", "D1"), ("main", "D7"), ("main", "D8"), ("main", "D9")}

    for ref, fp in sorted(fps.items()):
        entry = bom[ref]
        if not ref.startswith("D") or entry.mpn in ("BAT54S,215", "WS2812B-MINI-V3J"):
            continue
        nets = pad_nets(fp)
        assert set(nets) == {"1", "2"}, f"{board}:{ref} expected 2 pads (1=K, 2=A)"
        net_k, net_a = nets["1"], nets["2"]
        vk = NOMINAL_DC_VOLTS[net_k]
        va = NOMINAL_DC_VOLTS[net_a]

        if (board, ref) in forward_Conducting:
            assert va > vk, f"{board}:{ref} ({entry.mpn}) forward diode/LED reversed: V(A={net_a})={va} <= V(K={net_k})={vk}"
        elif (board, ref) in reverse_clamping:
            assert vk > va, f"{board}:{ref} ({entry.mpn}) clamp/catch/flyback diode forward-shorted at DC: V(K={net_k})={vk} <= V(A={net_a})={va}"
        else:
            pytest.fail(f"Unclassified 2-pin diode {board}:{ref} ({entry.mpn})")

        # Physical silkscreen cathode-mark proximity check in board coordinates
        pads_board = {
            p.GetNumber(): (pcbnew.ToMM(p.GetPosition().x), -pcbnew.ToMM(p.GetPosition().y))
            for p in fp.Pads() if p.GetNumber() in ("1", "2")
        }
        sx, sy = _silk_mark_centroid_board_mm(fp)
        dist_k = math.hypot(sx - pads_board["1"][0], sy - pads_board["1"][1])
        dist_a = math.hypot(sx - pads_board["2"][0], sy - pads_board["2"][1])
        assert dist_k + 0.35 < dist_a, (
            f"{board}:{ref} ({entry.mpn}) silkscreen cathode mark closer to Anode ({dist_a:.2f} mm) "
            f"than Cathode ({dist_k:.2f} mm)"
        )
