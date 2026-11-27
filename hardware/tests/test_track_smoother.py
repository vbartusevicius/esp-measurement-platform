"""Unit & integration tests for the DRC-safe octilinear track smoother
(`hardware/scripts/smooth_tracks.py`)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pcbnew
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "hardware/scripts"))
import smooth_tracks as st


def _make_board(w: float = 30.0, h: float = 30.0) -> tuple[pcbnew.BOARD, dict]:
    brd = pcbnew.BOARD()
    brd.SetCopperLayerCount(4)
    ds = brd.GetDesignSettings()
    ds.m_MinClearance = pcbnew.FromMM(0.2)
    ds.m_TrackMinWidth = pcbnew.FromMM(0.12)
    ds.m_CopperEdgeClearance = pcbnew.FromMM(0.3)
    for (x0, y0), (x1, y1) in (
        ((0, 0), (w, 0)), ((w, 0), (w, h)), ((w, h), (0, h)), ((0, h), (0, 0)),
    ):
        seg = pcbnew.PCB_SHAPE(brd, pcbnew.SHAPE_T_SEGMENT)
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(pcbnew.FromMM(0.05))
        seg.SetStart(pcbnew.VECTOR2I_MM(x0, -y0))
        seg.SetEnd(pcbnew.VECTOR2I_MM(x1, -y1))
        brd.Add(seg)
    plan = {
        "frame": {
            "size": {"x": w, "y": h},
            "edge_clearance": 0.3,
            "power_nets": [],
            "domain_regions": {"SELV": {"x0": 0.0, "y0": 0.0, "x1": w, "y1": h}},
            "fine_pitch_power_pads": [],
        }
    }
    return brd, plan


def _net(brd: pcbnew.BOARD, name: str) -> pcbnew.NETINFO_ITEM:
    existing = brd.FindNet(name)
    if existing and existing.GetNetCode() > 0:
        return existing
    ni = pcbnew.NETINFO_ITEM(brd, name)
    brd.Add(ni)
    return brd.FindNet(name)


def _add_track(brd: pcbnew.BOARD, net_obj, a, b, width: float = 0.2, layer=pcbnew.F_Cu, locked: bool = False):
    t = pcbnew.PCB_TRACK(brd)
    t.SetStart(pcbnew.VECTOR2I_MM(a[0], -a[1]))
    t.SetEnd(pcbnew.VECTOR2I_MM(b[0], -b[1]))
    t.SetWidth(pcbnew.FromMM(width))
    t.SetLayer(layer)
    t.SetLocked(locked)
    brd.Add(t)
    t.SetNet(net_obj)
    return t


def _add_pad(brd: pcbnew.BOARD, ref: str, net_obj, x: float, y: float, size: float = 1.0,
             shape=pcbnew.PAD_SHAPE_CIRCLE, drill: float = 0.0):
    fp = pcbnew.FOOTPRINT(brd)
    fp.SetReference(ref)
    fp.SetPosition(pcbnew.VECTOR2I_MM(x, -y))
    pad = pcbnew.PAD(fp)
    pad.SetNumber("1" if net_obj else "")
    pad.SetShape(shape)
    pad.SetSize(pcbnew.VECTOR2I_MM(size, size))
    pad.SetPosition(pcbnew.VECTOR2I_MM(x, -y))
    if drill > 0 and net_obj is None:
        pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(drill, drill))
        pad.SetLayerSet(pad.UnplatedHoleMask())
    elif drill > 0:
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(drill, drill))
        pad.SetLayerSet(pad.PTHMask())
    else:
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pad.SMDMask())
    fp.Add(pad)
    brd.Add(fp)
    if net_obj is not None:
        pad.SetNet(net_obj)
    return pad


def _add_via(brd: pcbnew.BOARD, net_obj, x: float, y: float, dia: float = 0.6, drill: float = 0.3):
    v = pcbnew.PCB_VIA(brd)
    v.SetPosition(pcbnew.VECTOR2I_MM(x, -y))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetWidth(pcbnew.FromMM(dia))
    v.SetDrill(pcbnew.FromMM(drill))
    brd.Add(v)
    v.SetNet(net_obj)
    return v


def _add_rule_keepout(brd: pcbnew.BOARD, x0: float, y0: float, x1: float, y1: float, layer=pcbnew.F_Cu):
    z = pcbnew.ZONE(brd)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(True)
    z.SetLayer(layer)
    out = z.Outline()
    out.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        p = pcbnew.VECTOR2I_MM(x, -y)
        out.Append(p.x, p.y)
    brd.Add(z)
    return z


def _traces(brd: pcbnew.BOARD, net_name: str):
    return [t for t in brd.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T and t.GetNetname() == net_name]


def test_v_detour_and_staircase_smoothing_with_midchain_neckdown_and_snapping():
    """Snaps endpoints within 0.015 mm, keeps degree-2 chain intact across a mid-chain
    width neckdown (0.20 -> 0.15 -> 0.20), and collapses V-detours and micro-staircases."""
    brd, plan = _make_board()
    sig1 = _net(brd, "SIG1")
    sig2 = _net(brd, "SIG2")

    # V-detour on SIG1 with a 0.010 mm endpoint snap offset AND mid-chain width neckdown
    _add_pad(brd, "P1", sig1, 4.0, 10.0)
    _add_pad(brd, "P2", sig1, 14.0, 10.0)
    _add_track(brd, sig1, (4.0, 10.0), (6.0, 10.0), width=0.20)
    _add_track(brd, sig1, (6.008, 10.0), (9.0, 13.0), width=0.15)  # 8 um snap + neckdown!
    _add_track(brd, sig1, (9.0, 13.0), (12.0, 10.0), width=0.15)
    _add_track(brd, sig1, (12.0, 10.0), (14.0, 10.0), width=0.20)

    # Micro-staircase on SIG2 -> clean 2-segment 45 + H dogleg
    _add_pad(brd, "P3", sig2, 4.0, 20.0)
    _add_pad(brd, "P4", sig2, 10.0, 22.0)
    for a, b in (((4, 20), (5, 20)), ((5, 20), (5, 21)), ((5, 21), (6, 21)), ((6, 21), (6, 22)), ((6, 22), (10, 22))):
        _add_track(brd, sig2, a, b, width=0.20)

    stats = st.smooth_board(brd, plan)
    assert stats["chains_smoothed"] == 2
    t1 = _traces(brd, "SIG1")
    assert len(t1) == 1
    assert pcbnew.ToMM(t1[0].GetLength()) == pytest.approx(10.0, abs=0.02)
    assert pcbnew.ToMM(t1[0].GetWidth()) == pytest.approx(0.15, abs=0.005)

    t2 = _traces(brd, "SIG2")
    assert len(t2) == 2
    assert sum(pcbnew.ToMM(t.GetLength()) for t in t2) == pytest.approx(2 * math.sqrt(2) + 4.0, abs=0.02)


def test_skips_pour_nets_and_caps_tuned_net_reduction():
    """Pour nets (GND) are untouched; tuned nets preserve large intentional meanders
    while still smoothing small micro-jogs <= max_tuned_reduction_mm."""
    brd, plan = _make_board()
    gnd = _net(brd, "GND")
    clk = _net(brd, "CLK")

    # Pour zone on GND
    z = pcbnew.ZONE(brd)
    z.SetLayer(pcbnew.In1_Cu)
    z.SetNet(gnd)
    out = z.Outline()
    out.NewOutline()
    for x, y in ((1, 1), (29, 1), (29, 29), (1, 29)):
        p = pcbnew.VECTOR2I_MM(x, -y)
        out.Append(p.x, p.y)
    brd.Add(z)

    # V-detour on GND must be skipped
    _add_pad(brd, "G1", gnd, 4.0, 6.0)
    _add_pad(brd, "G2", gnd, 12.0, 6.0)
    for a, b in (((4, 6), (8, 9)), ((8, 9), (12, 6))):
        _add_track(brd, gnd, a, b)

    # Large 4 mm tuning meander on CLK (cannot be collapsed under 1.0 mm cap) + tiny 0.2 mm micro-jog (is collapsed)
    _add_pad(brd, "C1", clk, 4.0, 15.0)
    _add_pad(brd, "C2", clk, 18.0, 15.0)
    pts_clk = [(4, 15), (6, 15), (6, 18), (8, 18), (8, 15), (12, 15), (12.3, 15.3), (12.6, 15), (18, 15)]
    for a, b in zip(pts_clk, pts_clk[1:]):
        _add_track(brd, clk, a, b)
    old_clk_len = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts_clk, pts_clk[1:]))

    st.smooth_board(brd, plan, tuned_nets={"CLK"}, max_tuned_reduction_mm=1.0)

    assert len(_traces(brd, "GND")) == 2
    new_clk_len = sum(pcbnew.ToMM(t.GetLength()) for t in _traces(brd, "CLK"))
    # Micro-jog removed (~0.25 mm saved), big 6 mm meander preserved!
    assert 0.15 < (old_clk_len - new_clk_len) < 1.0


def test_exact_circular_pad_clearance_vs_bounding_box():
    """Exact center-to-segment minus radius allows a valid 45-deg shortcut past a
    circular THT pad whose square bbox corner would falsely block it, while still
    rejecting a shortcut that actually violates the circle clearance."""
    brd, plan = _make_board()
    sig = _net(brd, "SIG")
    obs = _net(brd, "OBS")

    # Circular pad at (10.0, 10.0), diameter 2.0 mm (radius 1.0 mm).
    # 45-deg shortcut from (6.0, 8.0) to (14.0, 16.0) passes through (10.0, 12.0):
    # line y = x + 2 -> distance from (10, 10) to line is 2 / sqrt(2) = 1.4142 mm!
    # Exact copper gap = 1.4142 - 1.0 (pad_r) - 0.1 (track_r) = 0.314 mm >= 0.212 mm -> VALID!
    # Square bounding box [9..11, 9..11] corner (9, 11) is ON the line y = x + 2 (dist = 0 -> FALSE REJECT)!
    _add_pad(brd, "TH1", obs, 10.0, 10.0, size=2.0, shape=pcbnew.PAD_SHAPE_CIRCLE, drill=1.0)
    _add_pad(brd, "A1", sig, 6.0, 8.0, size=0.6)
    _add_pad(brd, "A2", sig, 14.0, 16.0, size=0.6)
    for a, b in (((6, 8), (6, 16)), ((6, 16), (14, 16))):
        _add_track(brd, sig, a, b, width=0.20)

    st.smooth_board(brd, plan)
    t_sig = _traces(brd, "SIG")
    assert len(t_sig) == 1, "Circular pad exact clearance should allow valid 45-deg shortcut"

    # Now place a closer circular pad on a second net that DOES violate exact clearance
    sig_bad = _net(brd, "SIG_BAD")
    _add_pad(brd, "TH2", obs, 20.0, 10.0, size=2.0, shape=pcbnew.PAD_SHAPE_CIRCLE, drill=1.0)
    _add_pad(brd, "B1", sig_bad, 16.0, 8.8, size=0.6)
    _add_pad(brd, "B2", sig_bad, 24.0, 16.8, size=0.6)
    # 45-deg line y = x - 7.2 -> dist to (20, 10) is 2.8/sqrt(2)? No: |20 - 10 - 7.2|/sqrt(2)?
    # Line through (16, 8.8) -> (24, 16.8): y - x = -7.2; at (20, 10), |10 - 20 + 7.2|/sqrt(2) = 1.98 mm;
    # Use (16, 7.6) -> (24, 15.6): y - x = -8.4 -> at (20, 10), |10 - 20 + 8.4|/sqrt(2) = 1.131 mm -> gap 0.03 mm < 0.212!
    brd2, plan2 = _make_board()
    sig2 = _net(brd2, "SIG2")
    obs2 = _net(brd2, "OBS2")
    _add_pad(brd2, "TH2", obs2, 20.0, 10.0, size=2.0, shape=pcbnew.PAD_SHAPE_CIRCLE, drill=1.0)
    _add_pad(brd2, "B1", sig2, 16.0, 7.6, size=0.6)
    _add_pad(brd2, "B2", sig2, 24.0, 15.6, size=0.6)
    for a, b in (((16.0, 7.6), (16.0, 15.6)), ((16.0, 15.6), (24.0, 15.6))):
        _add_track(brd2, sig2, a, b, width=0.20)
    st.smooth_board(brd2, plan2)
    assert len(_traces(brd2, "SIG2")) == 2, "Shortcut violating circular pad clearance must be rejected"


def test_rejects_keepout_npth_via_and_same_net_self_overlap():
    """Verify strict pre-commit rejection against rule-area keepouts, unnetted NPTH
    mounting holes, other-net vias, and non-local same-net copper self-overlap."""
    # 1. Rule-area keepout blocks straight shortcut
    brd, plan = _make_board()
    sig = _net(brd, "SIG")
    _add_pad(brd, "P1", sig, 4.0, 10.0)
    _add_pad(brd, "P2", sig, 14.0, 10.0)
    _add_rule_keepout(brd, 8.0, 8.0, 10.0, 12.0)
    for a, b in (((4, 10), (7, 14)), ((7, 14), (11, 14)), ((11, 14), (14, 10))):
        _add_track(brd, sig, a, b)
    st.smooth_board(brd, plan)
    # Shortcut cannot cross y=10 through [8..10, 8..12]
    assert all(not st._segs_intersect(pcbnew.ToMM(t.GetStart().x), -pcbnew.ToMM(t.GetStart().y),
                                      pcbnew.ToMM(t.GetEnd().x), -pcbnew.ToMM(t.GetEnd().y),
                                      9.0, 8.0, 9.0, 12.0) for t in _traces(brd, "SIG"))

    # 2. Unnetted NPTH mounting hole blocks straight shortcut
    brd, plan = _make_board()
    sig = _net(brd, "SIG")
    _add_pad(brd, "P1", sig, 4.0, 10.0)
    _add_pad(brd, "P2", sig, 14.0, 10.0)
    _add_pad(brd, "H1", None, 9.0, 10.0, size=2.5, drill=2.5)
    for a, b in (((4, 10), (7, 14)), ((7, 14), (11, 14)), ((11, 14), (14, 10))):
        _add_track(brd, sig, a, b)
    st.smooth_board(brd, plan)
    assert len(_traces(brd, "SIG")) >= 2

    # 3. Other-net via blocks straight shortcut
    brd, plan = _make_board()
    sig = _net(brd, "SIG")
    oth = _net(brd, "OTH")
    _add_pad(brd, "P1", sig, 4.0, 10.0)
    _add_pad(brd, "P2", sig, 14.0, 10.0)
    _add_via(brd, oth, 9.0, 10.0, dia=0.6, drill=0.3)
    for a, b in (((4, 10), (7, 13)), ((7, 13), (11, 13)), ((11, 13), (14, 10))):
        _add_track(brd, sig, a, b)
    st.smooth_board(brd, plan)
    for t in _traces(brd, "SIG"):
        d = st._dist_pt_seg(9.0, -10.0, pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y),
                            pcbnew.ToMM(t.GetEnd().x), pcbnew.ToMM(t.GetEnd().y))
        assert d >= 0.3 + 0.1 + 0.2

    # 4. Same-net non-local branch blocks a self-crossing shortcut
    brd, plan = _make_board()
    sig = _net(brd, "SIG")
    _add_pad(brd, "P1", sig, 4.0, 10.0)
    _add_pad(brd, "P2", sig, 14.0, 10.0)
    _add_pad(brd, "P3", sig, 9.0, 5.0)
    _add_pad(brd, "P4", sig, 9.0, 11.5)
    # Locked vertical same-net spur from (9, 5) to (9, 11.5) crosses y=10 at x=9
    _add_track(brd, sig, (9.0, 5.0), (9.0, 11.5), locked=True)
    for a, b in (((4, 10), (7, 14)), ((7, 14), (11, 14)), ((11, 14), (14, 10))):
        _add_track(brd, sig, a, b)
    st.smooth_board(brd, plan)
    for t in _traces(brd, "SIG"):
        if t.IsLocked():
            continue
        assert not st._segs_intersect(pcbnew.ToMM(t.GetStart().x), -pcbnew.ToMM(t.GetStart().y),
                                      pcbnew.ToMM(t.GetEnd().x), -pcbnew.ToMM(t.GetEnd().y),
                                      9.0, 5.0, 9.0, 11.5)


@pytest.mark.parametrize("board", ("main", "ui", "reader"))
def test_committed_boards_are_already_smoothed_idempotently(board):
    """Every committed routed board has already passed through `smooth_board`
    in `import_ses`: a second pass produces zero further changes."""
    import yaml

    pcb = pcbnew.LoadBoard(str(REPO / "hardware/layout/v1" / board / f"{board}.kicad_pcb"))
    plan = yaml.safe_load((REPO / "hardware/circuits/variants/v1" / f"layout_{board}.yaml").read_text())
    stats = st.smooth_board(pcb, plan)
    assert stats["chains_smoothed"] == 0, f"{board} still has unsmoothed chains: {stats}"
