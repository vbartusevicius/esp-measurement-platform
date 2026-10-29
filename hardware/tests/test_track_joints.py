"""Every track end must land solidly: on another track end, on another track's centreline (T joint),
inside a pad, inside a via or inside a filled zone of the same net and layer. An end whose round cap
only grazes a pad or track (KiCad counts that as connected, a fab makes a hairline joint) fails:
layout.py seat_track_ends() runs such ends into the pad / via / track."""

import math
import sys
from pathlib import Path

import pcbnew
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hardware/scripts"))
import release

TOL = pcbnew.FromMM(0.005)


def _on_segment(p, t):
    a, b = t.GetStart(), t.GetEnd()
    dx, dy = b.x - a.x, b.y - a.y
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return math.hypot(p.x - a.x, p.y - a.y) <= TOL
    u = max(0.0, min(1.0, ((p.x - a.x) * dx + (p.y - a.y) * dy) / length2))
    return math.hypot(p.x - (a.x + u * dx), p.y - (a.y + u * dy)) <= TOL


def loose_ends(board):
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())   # zone fills as DRC / the fab see them
    tracks = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
    vias = [v for v in board.GetTracks() if v.Type() == pcbnew.PCB_VIA_T]
    pads = list(board.GetPads())
    bad = []
    for t in tracks:
        for end in (t.GetStart(), t.GetEnd()):
            same = [o for o in tracks if o is not t and o.GetNetCode() == t.GetNetCode() and o.GetLayer() == t.GetLayer()]
            if any(_on_segment(end, o) for o in same):
                continue
            if any(v.GetNetCode() == t.GetNetCode() and math.hypot(end.x - v.GetPosition().x, end.y - v.GetPosition().y)
                   <= v.GetWidth(t.GetLayer()) / 2 for v in vias):
                continue
            if any(p.GetNetCode() == t.GetNetCode() and p.IsOnLayer(t.GetLayer()) and p.HitTest(end) for p in pads):
                continue
            if any(z.GetNetCode() == t.GetNetCode() and z.IsOnLayer(t.GetLayer()) and z.HitTestFilledArea(t.GetLayer(), end)
                   for z in board.Zones()):
                continue
            bad.append(f"{t.GetNetname()} {t.GetLayerName()} end at ({pcbnew.ToMM(end.x):.3f}, {-pcbnew.ToMM(end.y):.3f})")
    return bad


@pytest.mark.parametrize("board", release.BOARDS)
def test_track_ends_land_on_pads_tracks_or_vias(board):
    bad = loose_ends(pcbnew.LoadBoard(str(release.layout_path(board))))
    assert not bad, f"{board}: {len(bad)} track ends only graze their pad / track: " + "; ".join(bad[:8])
