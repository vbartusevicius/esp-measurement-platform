"""Unit & integration tests for 4-orientation per-pad modeling, shared-parent
pin attraction, zero-courtyard 180-deg uncrossing, and pin-pair midpoint
alignment in `hardware/scripts/placer.py`."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pcbnew
import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "hardware/scripts"))
import placer


def _net(brd: pcbnew.BOARD, name: str) -> pcbnew.NETINFO_ITEM:
    existing = brd.FindNet(name)
    if existing and existing.GetNetCode() > 0:
        return existing
    ni = pcbnew.NETINFO_ITEM(brd, name)
    brd.Add(ni)
    return brd.FindNet(name)


def _add_fp(
    brd: pcbnew.BOARD,
    ref: str,
    fpid_name: str,
    x: float,
    y: float,
    pads_spec: list[tuple[str, float, float, float, float, pcbnew.NETINFO_ITEM]],
    *,
    rot: float = 0.0,
    locked: bool = False,
    value: str = "",
) -> pcbnew.FOOTPRINT:
    fp = pcbnew.FOOTPRINT(brd)
    fp.SetReference(ref)
    fp.SetValue(value or fpid_name)
    fp.SetFPID(pcbnew.LIB_ID("TestLib", fpid_name))
    fp.SetPosition(pcbnew.VECTOR2I(0, 0))
    xs, ys = [], []
    for num, lx, ly, sx, sy, net_obj in pads_spec:
        pad = pcbnew.PAD(fp)
        pad.SetNumber(num)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pad.SMDMask())
        pad.SetSize(pcbnew.VECTOR2I_MM(sx, sy))
        pad.SetPosition(pcbnew.VECTOR2I_MM(lx, -ly))
        fp.Add(pad)
        pad.SetNet(net_obj)
        xs.extend((lx - sx / 2, lx + sx / 2))
        ys.extend((ly - sy / 2, ly + sy / 2))
    # Courtyard around pads (using PCB_SHAPE rect on F_CrtYd)
    rect = pcbnew.PCB_SHAPE(fp, pcbnew.SHAPE_T_RECT)
    rect.SetLayer(pcbnew.F_CrtYd)
    rect.SetWidth(pcbnew.FromMM(0.05))
    rect.SetStart(pcbnew.VECTOR2I_MM(min(xs) - 0.2, -(max(ys) + 0.2)))
    rect.SetEnd(pcbnew.VECTOR2I_MM(max(xs) + 0.2, -(min(ys) - 0.2)))
    fp.Add(rect)
    fp.SetOrientationDegrees(rot)
    fp.SetPosition(pcbnew.VECTOR2I_MM(x, -y))
    fp.SetLocked(locked)
    brd.Add(fp)
    return fp


def _pad_xy(fp: pcbnew.FOOTPRINT, num: str) -> tuple[float, float]:
    pad = next(p for p in fp.Pads() if p.GetNumber() == num)
    return pcbnew.ToMM(pad.GetPosition().x), -pcbnew.ToMM(pad.GetPosition().y)


def test_bypass_cap_next_to_ic_vcc_gnd_never_flips_toward_distant_board_gnd(tmp_path):
    """A 2-pin bypass cap placed next to an IC's adjacent VCC/GND pins must pull
    each pad straight to its matching IC pin and NEVER flip 180 deg toward a
    distant board ground connector."""
    brd = pcbnew.BOARD()
    vcc = _net(brd, "+3V3")
    gnd = _net(brd, "GND")

    # Parent IC U1 locked at (10, 12): adjacent pins on its right edge:
    #   Pin 1 (+3V3) at (11.5, 13.0)  [TOP]
    #   Pin 2 (GND)  at (11.5, 11.0)  [BOTTOM]
    u1 = _add_fp(
        brd, "U1", "SOT-23-5", 10.0, 12.0,
        [("1", 1.5, 1.0, 0.8, 0.6, vcc), ("2", 1.5, -1.0, 0.8, 0.6, gnd)],
        locked=True,
    )
    # Distant board ground connector J1 locked far ABOVE U1 at (26, 26)
    _add_fp(
        brd, "J1", "Conn_GND", 26.0, 26.0,
        [("1", -1.0, 0.0, 1.2, 1.2, gnd), ("2", 1.0, 0.0, 1.2, 1.2, gnd)],
        locked=True,
    )
    # Unlocked 0805 bypass cap C1 (Pad 1 = +3V3, Pad 2 = GND)
    c1 = _add_fp(
        brd, "C1", "C_0805_2012Metric", 5.0, 5.0,
        [("1", -0.95, 0.0, 1.0, 1.2, vcc), ("2", 0.95, 0.0, 1.0, 1.2, gnd)],
        locked=False, value="100n 50V",
    )

    plan = {
        "frame": {"size": {"x": 30.0, "y": 30.0}, "edge_clearance": 0.3},
        "heights": {"default": 1.2},
        "parts": {
            "U1": {"x": 10.0, "y": 12.0, "rot": 0, "block": "ic", "locked": True},
            "J1": {"x": 26.0, "y": 26.0, "rot": 0, "block": "conn", "locked": True},
        },
    }
    parts_json = tmp_path / "parts.json"
    parts_json.write_text(json.dumps([
        {"ref": "U1", "place": "ic"},
        {"ref": "J1", "place": "conn"},
        {"ref": "C1", "place": "ic"},
    ]))

    placer.solve_board(brd, plan, "test_bypass", parts_json)

    u_vcc, u_gnd = _pad_xy(u1, "1"), _pad_xy(u1, "2")
    c_vcc, c_gnd = _pad_xy(c1, "1"), _pad_xy(c1, "2")
    cx, cy = (c_vcc[0] + c_gnd[0]) * 0.5, (c_vcc[1] + c_gnd[1]) * 0.5

    # Must hug U1's VCC/GND pair, not drift toward distant J1 at (26, 26)
    assert math.hypot(cx - 11.5, cy - 12.0) < 4.5
    # Must NOT cross (c_vcc -> u_vcc) with (c_gnd -> u_gnd)
    assert not placer._segs_properly_cross(c_vcc, u_vcc, c_gnd, u_gnd)
    # Orientation must strictly beat its 180-deg flip relative to U1's pins
    d_cur = math.hypot(c_vcc[0] - u_vcc[0], c_vcc[1] - u_vcc[1]) + math.hypot(c_gnd[0] - u_gnd[0], c_gnd[1] - u_gnd[1])
    d_flp = math.hypot(c_gnd[0] - u_vcc[0], c_gnd[1] - u_vcc[1]) + math.hypot(c_vcc[0] - u_gnd[0], c_vcc[1] - u_gnd[1])
    assert d_cur <= d_flp + 1e-4


def test_uncross_and_align_flips_crossed_passive_aligns_midpoint_and_skips_polarized():
    """Post-placement pass flips an upside-down 0805 cap by 180 deg, aligns it to the
    shared parent's adjacent pin-pair midpoint when clash-free, and never flips a
    polarized diode or electrolytic capacitor."""
    brd = pcbnew.BOARD()
    vcc = _net(brd, "+5V")
    gnd = _net(brd, "GND")

    # Parent U1 with horizontal adjacent pin pair at y=10.0: Pin 1 (+5V) x=10.0, Pin 2 (GND) x=12.0 (mid x=11.0)
    u1 = _add_fp(
        brd, "U1", "IC_Test", 11.0, 10.0,
        [("1", -1.0, 0.0, 0.7, 0.7, vcc), ("2", 1.0, 0.0, 0.7, 0.7, gnd)],
        locked=True,
    )
    # C1 placed above U1 at (12.2, 13.0) — shifted 1.2 mm off midpoint AND upside-down (rot=180 -> Pad 1 on right!)
    c1 = _add_fp(
        brd, "C1", "C_0805_2012Metric", 12.2, 13.0,
        [("1", -0.95, 0.0, 1.0, 1.2, vcc), ("2", 0.95, 0.0, 1.0, 1.2, gnd)],
        rot=180.0, locked=False,
    )
    # Polarized diode D1 and electrolytic CP cap C2 also intentionally crossed: MUST NOT flip!
    d1 = _add_fp(
        brd, "D1", "D_SMA", 11.0, 5.0,
        [("1", -1.8, 0.0, 1.5, 1.5, gnd), ("2", 1.8, 0.0, 1.5, 1.5, vcc)],
        rot=0.0, locked=False,
    )
    c2 = _add_fp(
        brd, "C2", "CP_Radial_D5.0mm_P2.00mm", 22.0, 10.0,
        [("1", 1.0, 0.0, 1.2, 1.2, vcc), ("2", -1.0, 0.0, 1.2, 1.2, gnd)],
        rot=0.0, locked=False,
    )

    plan = {"frame": {"size": {"x": 30.0, "y": 30.0}, "edge_clearance": 0.3}}
    stats = placer.uncross_and_align_passives(brd, plan)
    assert stats["flipped"] == 1
    assert stats["aligned"] == 1

    # C1 uncrossed to rot=0 and centered on midpoint x=11.0
    assert round(c1.GetOrientation().AsDegrees()) % 360 == 0
    assert pcbnew.ToMM(c1.GetPosition().x) == pytest.approx(11.0, abs=0.06)
    assert not placer._segs_properly_cross(_pad_xy(c1, "1"), _pad_xy(u1, "1"), _pad_xy(c1, "2"), _pad_xy(u1, "2"))
    # Polarized D1 and C2 must remain untouched
    assert round(d1.GetOrientation().AsDegrees()) % 360 == 0
    assert round(c2.GetOrientation().AsDegrees()) % 360 == 0


@pytest.mark.parametrize("board", ("main", "ui", "reader"))
def test_committed_boards_have_zero_upside_down_symmetric_passives(board):
    """Every unlocked symmetric 2-pin passive on the committed boards is already
    uncrossed (0 beneficial 180-deg flips remaining)."""
    pcb = pcbnew.LoadBoard(str(REPO / "hardware/layout/v1" / board / f"{board}.kicad_pcb"))
    plan = yaml.safe_load((REPO / "hardware/circuits/variants/v1" / f"layout_{board}.yaml").read_text())
    stats = placer.uncross_and_align_passives(pcb, plan)
    assert stats["flipped"] == 0, f"{board} has {stats['flipped']} upside-down symmetric 2-pin passives"
