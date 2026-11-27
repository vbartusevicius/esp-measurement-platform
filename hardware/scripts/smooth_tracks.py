"""DRC-safe octilinear (0 / 45 / 90 deg) post-SES track smoother.

Eliminates autorouter V-detours and micro-staircase jogs right after importing
a Specctra `.ses` session and before saving / DRC scoring the final `.kicad_pcb`.

Key invariants:
  1. Per-net, per-layer chain extraction with 0.015 mm endpoint snapping; pins
     only branch junctions (deg != 2), pad centers, via centers, and locked
     track ends. Never splits a degree-2 chain on mid-chain width neckdowns.
  2. Skips copper pour/plane nets (`GND`); caps per-shortcut length reduction
     on length-matched / differential nets (`tuned_nets`) so intentional
     meanders stay intact.
  3. Greedy octilinear shortcutting over windows `j in [min(n-1, i+8)..i+2]`
     testing straight 0/45/90 segments and both 2-segment 45 + H/V doglegs.
  4. Strict pre-commit clearance verification against board edges/slots,
     unnetted mounting holes/cutouts, KiCad rule-area keepouts, all other-net
     tracks/vias (`GetWidth(F_Cu)`)/pads (exact center-to-segment minus radius
     for `PAD_SHAPE_CIRCLE`), domain creepage, and same-net self-crossing /
     non-local copper self-overlap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pcbnew
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

SNAP_TOL_MM = 0.015
SAFETY_MARGIN_MM = 0.012
TUNED_MAX_REDUCTION_MM = 1.0
MAX_WINDOW = 8
MAX_PASSES = 6
MIN_LEN_GAIN_MM = 0.002

# Removed PCB_TRACK objects must stay alive for the process lifetime in KiCad 10 SWIG.
_DETACHED: list[pcbnew.PCB_TRACK] = []


@dataclass(frozen=True)
class Seg:
    ax: float
    ay: float
    bx: float
    by: float
    width: float
    net_code: int
    net_name: str
    locked: bool = False

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        r = self.width * 0.5
        return (
            min(self.ax, self.bx) - r,
            min(self.ay, self.by) - r,
            max(self.ax, self.bx) + r,
            max(self.ay, self.by) + r,
        )


@dataclass(frozen=True)
class PadObs:
    kind: str  # "circle" | "oval" | "poly"
    net_code: int
    net_name: str
    cx: float
    cy: float
    radius: float
    ax: float = 0.0
    ay: float = 0.0
    bx: float = 0.0
    by: float = 0.0
    poly: Polygon | None = None
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    is_npth_hole: bool = False
    drill_r: float = 0.0


@dataclass(frozen=True)
class ViaObs:
    x: float
    y: float
    radius: float
    net_code: int
    net_name: str
    layers: frozenset[int]


def _dist_pt_seg(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 <= 1e-18:
        return math.hypot(px - ax, py - ay)
    u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + u * dx), py - (ay + u * dy))


def _orient(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _segs_intersect(ax: float, ay: float, bx: float, by: float,
                    cx: float, cy: float, dx: float, dy: float) -> bool:
    o1 = _orient(ax, ay, bx, by, cx, cy)
    o2 = _orient(ax, ay, bx, by, dx, dy)
    o3 = _orient(cx, cy, dx, dy, ax, ay)
    o4 = _orient(cx, cy, dx, dy, bx, by)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        return True
    eps = 1e-12
    if abs(o1) <= eps and min(ax, bx) - 1e-9 <= cx <= max(ax, bx) + 1e-9 and min(ay, by) - 1e-9 <= cy <= max(ay, by) + 1e-9:
        return True
    if abs(o2) <= eps and min(ax, bx) - 1e-9 <= dx <= max(ax, bx) + 1e-9 and min(ay, by) - 1e-9 <= dy <= max(ay, by) + 1e-9:
        return True
    if abs(o3) <= eps and min(cx, dx) - 1e-9 <= ax <= max(cx, dx) + 1e-9 and min(cy, dy) - 1e-9 <= ay <= max(cy, dy) + 1e-9:
        return True
    if abs(o4) <= eps and min(cx, dx) - 1e-9 <= bx <= max(cx, dx) + 1e-9 and min(cy, dy) - 1e-9 <= by <= max(cy, dy) + 1e-9:
        return True
    return False


def _dist_seg_seg(ax: float, ay: float, bx: float, by: float,
                  cx: float, cy: float, dx: float, dy: float) -> float:
    if _segs_intersect(ax, ay, bx, by, cx, cy, dx, dy):
        return 0.0
    return min(
        _dist_pt_seg(ax, ay, cx, cy, dx, dy),
        _dist_pt_seg(bx, by, cx, cy, dx, dy),
        _dist_pt_seg(cx, cy, ax, ay, bx, by),
        _dist_pt_seg(dx, dy, ax, ay, bx, by),
    )


def _pad_to_obs(pad: pcbnew.PAD) -> PadObs:
    pos = pad.GetPosition()
    cx, cy = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
    sx, sy = pcbnew.ToMM(pad.GetSizeX()), pcbnew.ToMM(pad.GetSizeY())
    drill_r = max(pcbnew.ToMM(pad.GetDrillSizeX()), pcbnew.ToMM(pad.GetDrillSizeY())) * 0.5
    net_code = pad.GetNetCode()
    net_name = pad.GetNetname()
    is_npth = drill_r > 0 and net_code == 0
    shape = pad.GetShape()

    if shape == pcbnew.PAD_SHAPE_CIRCLE or is_npth:
        r = max(sx * 0.5, sy * 0.5, drill_r)
        return PadObs(
            kind="circle", net_code=net_code, net_name=net_name,
            cx=cx, cy=cy, radius=r,
            bbox=(cx - r, cy - r, cx + r, cy + r),
            is_npth_hole=is_npth, drill_r=drill_r,
        )

    angle_rad = -math.radians(pad.GetOrientation().AsDegrees())
    ca, sa = math.cos(angle_rad), math.sin(angle_rad)

    if shape == pcbnew.PAD_SHAPE_OVAL:
        r = min(sx, sy) * 0.5
        half_span = max(0.0, max(sx, sy) * 0.5 - r)
        if sx >= sy:
            ux, uy = ca, sa
        else:
            ux, uy = -sa, ca
        ax, ay = cx - ux * half_span, cy - uy * half_span
        bx, by = cx + ux * half_span, cy + uy * half_span
        return PadObs(
            kind="oval", net_code=net_code, net_name=net_name,
            cx=cx, cy=cy, radius=r, ax=ax, ay=ay, bx=bx, by=by,
            bbox=(min(ax, bx) - r, min(ay, by) - r, max(ax, bx) + r, max(ay, by) + r),
            drill_r=drill_r,
        )

    hx, hy = sx * 0.5, sy * 0.5
    corners = []
    for lx, ly in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)):
        corners.append((cx + lx * ca - ly * sa, cy + lx * sa + ly * ca))
    poly = Polygon(corners)
    bx0, by0, bx1, by1 = poly.bounds
    return PadObs(
        kind="poly", net_code=net_code, net_name=net_name,
        cx=cx, cy=cy, radius=0.0, poly=poly, bbox=(bx0, by0, bx1, by1),
        drill_r=drill_r,
    )


def _pad_distance(obs: PadObs, ax: float, ay: float, bx: float, by: float) -> float:
    if obs.kind == "circle":
        return max(0.0, _dist_pt_seg(obs.cx, obs.cy, ax, ay, bx, by) - obs.radius)
    if obs.kind == "oval":
        return max(0.0, _dist_seg_seg(ax, ay, bx, by, obs.ax, obs.ay, obs.bx, obs.by) - obs.radius)
    assert obs.poly is not None
    return LineString([(ax, ay), (bx, by)]).distance(obs.poly)


def _zone_polygons_mm(zone: pcbnew.ZONE) -> list[Polygon]:
    polys: list[Polygon] = []
    pset = zone.Outline()
    for oi in range(pset.OutlineCount()):
        ring = pset.Outline(oi)
        if ring.PointCount() < 3:
            continue
        pts = [(pcbnew.ToMM(ring.CPoint(pi).x), pcbnew.ToMM(ring.CPoint(pi).y)) for pi in range(ring.PointCount())]
        p = Polygon(pts)
        if p.is_valid and p.area > 1e-6:
            polys.append(p)
    return polys


def octilinear_candidates(a: tuple[float, float], b: tuple[float, float]) -> list[list[tuple[float, float]]]:
    """Return octilinear (0 / 45 / 90 deg) replacement polylines from `a` to `b`:
    either a single straight 0/45/90 segment, or both 2-segment 45 + H/V doglegs."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    adx, ady = abs(dx), abs(dy)
    if adx < 1e-6 and ady < 1e-6:
        return []
    if adx < 1e-4 or ady < 1e-4 or abs(adx - ady) < 1e-4:
        return [[a, b]]
    diag = min(adx, ady)
    sx = 1.0 if dx > 0 else -1.0
    sy = 1.0 if dy > 0 else -1.0
    m1 = (round(ax + sx * diag, 6), round(ay + sy * diag, 6))
    m2 = (round(bx - sx * diag, 6), round(by - sy * diag, 6))
    return [[a, m1, b], [a, m2, b]]


def _polyline_len(pts: list[tuple[float, float]]) -> float:
    return sum(math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]) for k in range(len(pts) - 1))


def _aabb_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float], margin: float) -> bool:
    return not (a[2] + margin < b[0] or b[2] + margin < a[0] or a[3] + margin < b[1] or b[3] + margin < a[1])


def _extract_net_rules(board: pcbnew.BOARD, plan: dict | None) -> tuple[dict[str, float], dict[str, str], dict[str, float], list[Polygon]]:
    """Return `(net_clearance_mm, net_domain, net_min_open_width_mm, fine_pitch_courtyards)`."""
    ds = board.GetDesignSettings()
    default_clr = max(0.2, pcbnew.ToMM(ds.m_MinClearance))
    min_track = max(0.12, pcbnew.ToMM(ds.m_TrackMinWidth))

    net_clr: dict[str, float] = {}
    net_dom: dict[str, str] = {}
    net_min_w: dict[str, float] = {}
    fp_courtyards: list[Polygon] = []

    if plan:
        frame = plan["frame"]
        power_nets = set(frame.get("power_nets", []))
        regions = frame.get("domain_regions", {})
        fine_refs = set(frame.get("fine_pitch_power_pads", []))
        for fp in board.Footprints():
            if fp.GetReference() in fine_refs:
                fp.BuildCourtyardCaches()
                bb = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd).BBox()
                fp_courtyards.append(Polygon([
                    (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop())),
                    (pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetTop())),
                    (pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())),
                    (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetBottom())),
                ]))
            for pad in fp.Pads():
                n = pad.GetNetname()
                if not n or n in net_dom:
                    continue
                px, py = pcbnew.ToMM(pad.GetPosition().x), -pcbnew.ToMM(pad.GetPosition().y)
                for dom, areas in regions.items():
                    alist = areas if isinstance(areas, list) else [areas]
                    if any(r["x0"] <= px <= r["x1"] and r["y0"] <= py <= r["y1"] for r in alist):
                        net_dom[n] = dom
                        break
        for n, dom in net_dom.items():
            if dom == "RELAY" and n in power_nets:
                net_clr[n] = 2.5
                net_min_w[n] = 0.75
            elif n in power_nets:
                net_clr[n] = default_clr
                net_min_w[n] = 0.22
            else:
                net_clr[n] = default_clr
                net_min_w[n] = min_track

    return net_clr, net_dom, net_min_w, fp_courtyards


class _BoardContext:
    def __init__(self, board: pcbnew.BOARD, plan: dict | None):
        self.board = board
        self.plan = plan
        ds = board.GetDesignSettings()
        self.default_clr = max(0.2, pcbnew.ToMM(ds.m_MinClearance))
        self.edge_clr = max(0.25, pcbnew.ToMM(ds.m_CopperEdgeClearance))
        if plan:
            self.edge_clr = max(self.edge_clr, float(plan["frame"].get("edge_clearance", 0.3)))
        self.hole_clr = max(0.30, self.default_clr)

        self.net_clr, self.net_dom, self.net_min_w, self.fp_courtyards = _extract_net_rules(board, plan)

        # Copper layers enabled
        self.cu_layers = [l for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu) if board.IsLayerEnabled(l)]

        # Board outline polygon + all Edge.Cuts segments (including milled isolation slots!)
        self.edge_segs: list[tuple[float, float, float, float]] = []
        for d in board.GetDrawings():
            if d.GetLayer() == pcbnew.Edge_Cuts and isinstance(d, pcbnew.PCB_SHAPE):
                if d.GetShape() == pcbnew.SHAPE_T_SEGMENT:
                    s, e = d.GetStart(), d.GetEnd()
                    self.edge_segs.append((pcbnew.ToMM(s.x), pcbnew.ToMM(s.y), pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)))

        self.outline_poly: Polygon | None = None
        if plan:
            frame = plan["frame"]
            if "outline" in frame:
                self.outline_poly = Polygon([(x, -y) for x, y in frame["outline"]])
            else:
                w, h = frame["size"]["x"], frame["size"]["y"]
                self.outline_poly = Polygon([(0.0, 0.0), (w, 0.0), (w, -h), (0.0, -h)])
            for slot in frame.get("slots", []):
                sp = Polygon([(slot["x0"], -slot["y0"]), (slot["x1"], -slot["y0"]),
                              (slot["x1"], -slot["y1"]), (slot["x0"], -slot["y1"])])
                self.outline_poly = self.outline_poly.difference(sp)

        # Rule-area keepouts per layer (z.GetIsRuleArea() and DoNotAllowTracks)
        self.keepouts: dict[int, list[Polygon]] = {l: [] for l in self.cu_layers}
        self.pour_nets: set[str] = set()
        for idx in range(board.GetAreaCount()):
            z = board.GetArea(idx)
            if z.GetIsRuleArea():
                if z.GetDoNotAllowTracks():
                    zpolys = _zone_polygons_mm(z)
                    for l in self.cu_layers:
                        if z.IsOnLayer(l):
                            self.keepouts[l].extend(zpolys)
            elif z.GetNetname():
                self.pour_nets.add(z.GetNetname())

        # Pads per layer + unnetted NPTH mounting holes (affect every copper layer)
        self.pads_by_layer: dict[int, list[PadObs]] = {l: [] for l in self.cu_layers}
        self.npth_holes: list[PadObs] = []
        for pad in board.GetPads():
            obs = _pad_to_obs(pad)
            if obs.is_npth_hole:
                self.npth_holes.append(obs)
                continue
            for l in self.cu_layers:
                if pad.IsOnLayer(l):
                    self.pads_by_layer[l].append(obs)

        # Vias (use GetWidth(F_Cu) as required)
        self.vias: list[ViaObs] = []
        self.arcs_by_layer: dict[int, list[Seg]] = {l: [] for l in self.cu_layers}
        for item in board.GetTracks():
            if item.Type() == pcbnew.PCB_VIA_T:
                pos = item.GetPosition()
                top, bot = item.TopLayer(), item.BottomLayer()
                lyrs = frozenset(self.cu_layers) if (top == pcbnew.F_Cu and bot == pcbnew.B_Cu) else frozenset((top, bot))
                self.vias.append(ViaObs(
                    x=pcbnew.ToMM(pos.x), y=pcbnew.ToMM(pos.y),
                    radius=pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)) * 0.5,
                    net_code=item.GetNetCode(), net_name=item.GetNetname(),
                    layers=lyrs,
                ))
            elif item.Type() == pcbnew.PCB_ARC_T:
                # Approximate any arc by chord segments for clearance checks
                s, m, e = item.GetStart(), item.GetMid(), item.GetEnd()
                w = pcbnew.ToMM(item.GetWidth())
                l = item.GetLayer()
                nc, nn = item.GetNetCode(), item.GetNetname()
                self.arcs_by_layer.setdefault(l, []).append(
                    Seg(pcbnew.ToMM(s.x), pcbnew.ToMM(s.y), pcbnew.ToMM(m.x), pcbnew.ToMM(m.y), w, nc, nn, True)
                )
                self.arcs_by_layer[l].append(
                    Seg(pcbnew.ToMM(m.x), pcbnew.ToMM(m.y), pcbnew.ToMM(e.x), pcbnew.ToMM(e.y), w, nc, nn, True)
                )

    def pair_clearance(self, net_a: str, net_b: str) -> float:
        dom_a, dom_b = self.net_dom.get(net_a), self.net_dom.get(net_b)
        if dom_a and dom_b and dom_a != dom_b:
            return 6.0 + SAFETY_MARGIN_MM
        ca = self.net_clr.get(net_a, self.default_clr)
        cb = self.net_clr.get(net_b, self.default_clr)
        return max(ca, cb) + SAFETY_MARGIN_MM

    def min_legal_width(self, net_name: str, sub_widths: list[float], cand_segs: list[tuple[tuple[float, float], tuple[float, float]]]) -> float:
        """Use `min(sub_widths)` across a smoothed sub-chain; if any segment exits
        fine-pitch courtyards, clamp up to the net's open-board DRU minimum width."""
        w_min = min(sub_widths)
        open_min = self.net_min_w.get(net_name, 0.12)
        if w_min >= open_min - 1e-6:
            return w_min
        if self.fp_courtyards:
            all_inside = True
            for a, b in cand_segs:
                ls = LineString([a, b])
                if not any(ls.intersects(c) for c in self.fp_courtyards):
                    all_inside = False
                    break
            if all_inside:
                return w_min
        return max(w_min, open_min)

    def segment_clears(
        self,
        layer: int,
        net_code: int,
        net_name: str,
        a: tuple[float, float],
        b: tuple[float, float],
        width: float,
        layer_segs: list[Seg],
        ignore_same_indices: set[int],
        adjacent_same_segs: list[tuple[tuple[float, float], tuple[float, float]]],
    ) -> bool:
        ax, ay = a
        bx, by = b
        half_w = width * 0.5
        s_bbox = (min(ax, bx) - half_w, min(ay, by) - half_w, max(ax, bx) + half_w, max(ay, by) + half_w)

        # 1. Board outline containment + Edge.Cuts / slot clearance
        if self.outline_poly is not None:
            mx, my = (ax + bx) * 0.5, (ay + by) * 0.5
            if not self.outline_poly.contains(Point(mx, my)):
                return False
        edge_req = half_w + self.edge_clr + SAFETY_MARGIN_MM
        for ex0, ey0, ex1, ey1 in self.edge_segs:
            if _dist_seg_seg(ax, ay, bx, by, ex0, ey0, ex1, ey1) < edge_req:
                return False

        # 2. Unnetted mounting holes / NPTH cutouts
        for hole in self.npth_holes:
            req = half_w + self.hole_clr + SAFETY_MARGIN_MM
            if _aabb_overlap(s_bbox, hole.bbox, req) and _pad_distance(hole, ax, ay, bx, by) < req:
                return False

        # 3. KiCad rule-area keepouts (DoNotAllowTracks)
        ko_req = half_w + SAFETY_MARGIN_MM
        line = None
        for kp in self.keepouts.get(layer, ()):
            kb = kp.bounds
            if _aabb_overlap(s_bbox, kb, ko_req):
                if line is None:
                    line = LineString([a, b])
                if line.distance(kp) < ko_req:
                    return False

        # 4. Pads on this layer (other-net clearance + avoid crossing unrelated same-net pads)
        for pad in self.pads_by_layer.get(layer, ()):
            if pad.net_code == net_code:
                # Allow touching same-net pads at the segment's own endpoints; reject cutting across
                # an unrelated same-net pad mid-segment.
                if (math.hypot(pad.cx - ax, pad.cy - ay) <= max(0.06, pad.radius + 0.06)
                        or math.hypot(pad.cx - bx, pad.cy - by) <= max(0.06, pad.radius + 0.06)):
                    continue
                if _aabb_overlap(s_bbox, pad.bbox, half_w) and _pad_distance(pad, ax, ay, bx, by) < half_w:
                    return False
                continue
            req = half_w + self.pair_clearance(net_name, pad.net_name)
            if _aabb_overlap(s_bbox, pad.bbox, req) and _pad_distance(pad, ax, ay, bx, by) < req:
                return False

        # 5. Vias spanning this layer (using GetWidth(F_Cu))
        for via in self.vias:
            if layer not in via.layers:
                continue
            if via.net_code == net_code:
                if (math.hypot(via.x - ax, via.y - ay) <= via.radius + 0.06
                        or math.hypot(via.x - bx, via.y - by) <= via.radius + 0.06):
                    continue
                if _dist_pt_seg(via.x, via.y, ax, ay, bx, by) < half_w + via.radius:
                    return False
                continue
            req = half_w + via.radius + self.pair_clearance(net_name, via.net_name)
            if _dist_pt_seg(via.x, via.y, ax, ay, bx, by) < req:
                return False

        # 6. All tracks on this layer (other-net clearance + same-net non-local self-overlap/crossing)
        all_segs = layer_segs + self.arcs_by_layer.get(layer, [])
        n_main = len(layer_segs)
        for idx, seg in enumerate(all_segs):
            if idx < n_main and idx in ignore_same_indices:
                continue
            if seg.net_code != net_code:
                req = half_w + seg.width * 0.5 + self.pair_clearance(net_name, seg.net_name)
                if _aabb_overlap(s_bbox, seg.bbox, req):
                    if _dist_seg_seg(ax, ay, bx, by, seg.ax, seg.ay, seg.bx, seg.by) < req:
                        return False
            else:
                # Same-net track: check if it shares an endpoint with (a, b)
                shares_a = (math.hypot(seg.ax - ax, seg.ay - ay) <= 0.005
                            or math.hypot(seg.bx - ax, seg.by - ay) <= 0.005)
                shares_b = (math.hypot(seg.ax - bx, seg.ay - by) <= 0.005
                            or math.hypot(seg.bx - bx, seg.by - by) <= 0.005)
                if shares_a and shares_b:
                    return False  # exact parallel duplicate segment
                if shares_a or shares_b:
                    # Reject hairpin fold-back onto adjacent segment (dot product > 0.96 -> angle < ~16 deg)
                    shared = a if shares_a else b
                    other_c = b if shares_a else a
                    other_s = (seg.bx, seg.by) if math.hypot(seg.ax - shared[0], seg.ay - shared[1]) <= 0.005 else (seg.ax, seg.ay)
                    vcx, vcy = other_c[0] - shared[0], other_c[1] - shared[1]
                    vsx, vsy = other_s[0] - shared[0], other_s[1] - shared[1]
                    lc, ls_len = math.hypot(vcx, vcy), math.hypot(vsx, vsy)
                    if lc > 1e-6 and ls_len > 1e-6 and (vcx * vsx + vcy * vsy) / (lc * ls_len) > 0.96:
                        return False
                    continue
                # Non-adjacent same-net segment: reject crossing or non-local copper self-overlap
                min_self = half_w + seg.width * 0.5 + 0.005
                if _aabb_overlap(s_bbox, seg.bbox, min_self):
                    if _dist_seg_seg(ax, ay, bx, by, seg.ax, seg.ay, seg.bx, seg.by) < min_self:
                        return False

        # 7. Reject hairpin fold-back against the immediately adjacent segments of the same chain
        for adj_a, adj_b in adjacent_same_segs:
            shared = a if (math.hypot(adj_a[0] - ax, adj_a[1] - ay) <= 0.005 or math.hypot(adj_b[0] - ax, adj_b[1] - ay) <= 0.005) else b
            other_c = b if shared == a else a
            other_s = adj_b if math.hypot(adj_a[0] - shared[0], adj_a[1] - shared[1]) <= 0.005 else adj_a
            vcx, vcy = other_c[0] - shared[0], other_c[1] - shared[1]
            vsx, vsy = other_s[0] - shared[0], other_s[1] - shared[1]
            lc, ls_len = math.hypot(vcx, vcy), math.hypot(vsx, vsy)
            if lc > 1e-6 and ls_len > 1e-6 and (vcx * vsx + vcy * vsy) / (lc * ls_len) > 0.96:
                return False

        return True


def _snap_points(
    raw_endpoints: list[tuple[float, float]],
    anchors: list[tuple[float, float]],
    tol: float = SNAP_TOL_MM,
) -> tuple[list[tuple[float, float]], list[int]]:
    """Cluster endpoints within `tol` mm, preferring exact pad/via/locked anchor
    coordinates when an endpoint falls within `tol` of an anchor."""
    nodes: list[tuple[float, float]] = list(anchors)
    indices: list[int] = []
    for px, py in raw_endpoints:
        best_i = -1
        best_d = tol
        for idx, (nx, ny) in enumerate(nodes):
            d = math.hypot(px - nx, py - ny)
            if d <= best_d:
                best_d = d
                best_i = idx
        if best_i >= 0:
            indices.append(best_i)
        else:
            indices.append(len(nodes))
            nodes.append((px, py))
    return nodes, indices


def extract_chains(
    segs: list[tuple[int, Seg]],
    anchors: list[tuple[float, float]],
    snap_tol: float = SNAP_TOL_MM,
) -> list[tuple[list[tuple[float, float]], list[float], list[int]]]:
    """Extract maximal degree-2 polyline chains from unlocked same-net, same-layer
    segments `(global_idx, Seg)`.

    Returns a list of `(points, seg_widths, global_seg_indices)` where each chain
    starts and ends at pinned nodes (deg != 2, pad/via centers, or locked track ends)
    and never splits on mid-chain width neckdowns.
    """
    if not segs:
        return []
    raw_pts: list[tuple[float, float]] = []
    for _, s in segs:
        raw_pts.append((s.ax, s.ay))
        raw_pts.append((s.bx, s.by))
    nodes, node_ids = _snap_points(raw_pts, anchors, tol=snap_tol)
    n_anchors = len(anchors)

    adj: dict[int, list[tuple[int, int, float, int]]] = {}
    for local_i, (gidx, s) in enumerate(segs):
        u = node_ids[2 * local_i]
        v = node_ids[2 * local_i + 1]
        if u == v:
            continue
        adj.setdefault(u, []).append((local_i, v, s.width, gidx))
        adj.setdefault(v, []).append((local_i, u, s.width, gidx))

    pinned = {u for u, inc in adj.items() if len(inc) != 2 or u < n_anchors}
    visited_edge: set[int] = set()
    chains: list[tuple[list[tuple[float, float]], list[float], list[int]]] = []

    def walk_from(start_u: int, first_edge: tuple[int, int, float, int]) -> None:
        e_id, nxt, w, gidx = first_edge
        visited_edge.add(e_id)
        pts = [nodes[start_u], nodes[nxt]]
        widths = [w]
        gidxs = [gidx]
        cur = nxt
        while cur not in pinned:
            rem = [e for e in adj[cur] if e[0] not in visited_edge]
            if not rem:
                break
            e_id, nxt, w, gidx = rem[0]
            visited_edge.add(e_id)
            pts.append(nodes[nxt])
            widths.append(w)
            gidxs.append(gidx)
            cur = nxt
            if cur == start_u:
                break
        chains.append((pts, widths, gidxs))

    for u in sorted(pinned):
        for edge in adj.get(u, ()):
            if edge[0] not in visited_edge:
                walk_from(u, edge)

    # Pure unpinned closed loops (rare, handle gracefully)
    for u in sorted(adj):
        for edge in adj[u]:
            if edge[0] not in visited_edge:
                walk_from(u, edge)

    return chains


def smooth_chain(
    pts: list[tuple[float, float]],
    widths: list[float],
    gidxs: list[int],
    ctx: _BoardContext,
    layer: int,
    net_code: int,
    net_name: str,
    layer_segs: list[Seg],
    *,
    max_len_reduction_mm: float | None = None,
) -> tuple[list[tuple[float, float]], list[float], bool]:
    """Greedily shortcut sub-chains `p[i..j]` (`j` from `min(len-1, i+8)` down to `i+2`)
    with 0/45/90 straight segments or 2-segment 45 + H/V doglegs."""
    cur_pts = list(pts)
    cur_widths = list(widths)
    cur_gidxs = list(gidxs)
    changed = False

    for _ in range(MAX_PASSES):
        pass_changed = False
        i = 0
        while i < len(cur_pts) - 2:
            accepted = False
            j_hi = min(len(cur_pts) - 1, i + MAX_WINDOW)
            for j in range(j_hi, i + 1, -1):
                sub_pts = cur_pts[i:j + 1]
                old_len = _polyline_len(sub_pts)
                old_segs = j - i
                sub_widths = cur_widths[i:j]

                # Build candidates ordered by (length, num_segs)
                cands = octilinear_candidates(cur_pts[i], cur_pts[j])
                if not cands:
                    continue

                # Active indices of this sub-chain in layer_segs to exclude during self-check
                ignore_set = set(cur_gidxs[i:j])

                # Also check against OTHER untouched segments of this chain that may already have
                # been rewritten earlier in this pass (live_chain_segs)
                adj_segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
                if i > 0:
                    adj_segs.append((cur_pts[i - 1], cur_pts[i]))
                if j < len(cur_pts) - 1:
                    adj_segs.append((cur_pts[j], cur_pts[j + 1]))

                for cand_pts in cands:
                    new_len = _polyline_len(cand_pts)
                    new_segs = len(cand_pts) - 1
                    shorter = new_len < old_len - MIN_LEN_GAIN_MM
                    fewer_same_len = (new_len <= old_len + MIN_LEN_GAIN_MM) and (new_segs < old_segs)
                    if not (shorter or fewer_same_len):
                        continue
                    if max_len_reduction_mm is not None and (old_len - new_len) > max_len_reduction_mm:
                        continue

                    cand_seg_pairs = [(cand_pts[k], cand_pts[k + 1]) for k in range(new_segs)]
                    w_cand = ctx.min_legal_width(net_name, sub_widths, cand_seg_pairs)

                    # Verify every candidate segment clears all board/keepout/other-net/same-net rules
                    ok = True
                    for k, (ca, cb) in enumerate(cand_seg_pairs):
                        # Adjacent segments for this piece (include the other half of a 2-seg dogleg)
                        local_adj = list(adj_segs)
                        if new_segs == 2:
                            other_pair = cand_seg_pairs[1 - k]
                            local_adj.append(other_pair)
                        if not ctx.segment_clears(layer, net_code, net_name, ca, cb, w_cand,
                                                  layer_segs, ignore_set, local_adj):
                            ok = False
                            break
                    if not ok:
                        continue

                    # Verify candidate doesn't cross/overlap untouched segments of THIS chain
                    for k_seg in range(len(cur_pts) - 1):
                        if i <= k_seg < j:
                            continue
                        oa, ob = cur_pts[k_seg], cur_pts[k_seg + 1]
                        ow = cur_widths[k_seg]
                        for ca, cb in cand_seg_pairs:
                            if (math.hypot(oa[0] - ca[0], oa[1] - ca[1]) <= 0.005
                                    or math.hypot(ob[0] - ca[0], ob[1] - ca[1]) <= 0.005
                                    or math.hypot(oa[0] - cb[0], oa[1] - cb[1]) <= 0.005
                                    or math.hypot(ob[0] - cb[0], ob[1] - cb[1]) <= 0.005):
                                continue
                            if _dist_seg_seg(ca[0], ca[1], cb[0], cb[1], oa[0], oa[1], ob[0], ob[1]) < (w_cand + ow) * 0.5 + 0.005:
                                ok = False
                                break
                        if not ok:
                            break
                    if not ok:
                        continue

                    # Commit shortcut into `layer_segs` live table (mark replaced entries degenerate & append new)
                    for idx_old in cur_gidxs[i:j]:
                        layer_segs[idx_old] = Seg(0.0, 0.0, 0.0, 0.0, 0.0, -1, "", False)
                    new_gidxs = []
                    for ca, cb in cand_seg_pairs:
                        new_gidxs.append(len(layer_segs))
                        layer_segs.append(Seg(ca[0], ca[1], cb[0], cb[1], w_cand, net_code, net_name, False))

                    cur_pts = cur_pts[:i] + cand_pts + cur_pts[j + 1:]
                    cur_widths = cur_widths[:i] + [w_cand] * new_segs + cur_widths[j:]
                    cur_gidxs = cur_gidxs[:i] + new_gidxs + cur_gidxs[j:]
                    changed = True
                    pass_changed = True
                    accepted = True
                    break
                if accepted:
                    break
            i += 1
        if not pass_changed:
            break

    return cur_pts, cur_widths, changed


def _smooth_board_once(
    board: pcbnew.BOARD,
    plan: dict | None = None,
    *,
    tuned_nets: set[str] | None = None,
    max_tuned_reduction_mm: float = TUNED_MAX_REDUCTION_MM,
) -> dict[str, float]:
    ctx = _BoardContext(board, plan)
    tuned = tuned_nets or set()

    # Collect straight PCB_TRACE_T segments per layer
    tracks_by_layer: dict[int, list[pcbnew.PCB_TRACK]] = {l: [] for l in ctx.cu_layers}
    layer_segs: dict[int, list[Seg]] = {l: [] for l in ctx.cu_layers}
    for item in board.GetTracks():
        if item.Type() != pcbnew.PCB_TRACE_T:
            continue
        lyr = item.GetLayer()
        if lyr not in tracks_by_layer:
            continue
        s, e = item.GetStart(), item.GetEnd()
        tracks_by_layer[lyr].append(item)
        layer_segs[lyr].append(Seg(
            pcbnew.ToMM(s.x), pcbnew.ToMM(s.y),
            pcbnew.ToMM(e.x), pcbnew.ToMM(e.y),
            pcbnew.ToMM(item.GetWidth()),
            item.GetNetCode(), item.GetNetname(), item.IsLocked(),
        ))

    segs_before = 0
    segs_after = 0
    len_before = 0.0
    len_after = 0.0
    chains_smoothed = 0

    for lyr in ctx.cu_layers:
        l_segs = layer_segs[lyr]
        l_tracks = tracks_by_layer[lyr]
        # Group unlocked segments by net_code (skip plane/pour nets and unnetted)
        by_net: dict[tuple[int, str], list[tuple[int, Seg]]] = {}
        for idx, s in enumerate(l_segs):
            if s.locked or s.net_code <= 0 or s.net_name in ctx.pour_nets:
                continue
            by_net.setdefault((s.net_code, s.net_name), []).append((idx, s))

        for (net_code, net_name), net_segs in sorted(by_net.items(), key=lambda kv: kv[0][1]):
            # Pin exact pad centers, via centers, and locked track endpoints on this net & layer
            anchors: list[tuple[float, float]] = []
            for p in ctx.pads_by_layer.get(lyr, ()):
                if p.net_code == net_code:
                    anchors.append((p.cx, p.cy))
            for v in ctx.vias:
                if v.net_code == net_code and lyr in v.layers:
                    anchors.append((v.x, v.y))
            for s in l_segs:
                if s.locked and s.net_code == net_code:
                    anchors.append((s.ax, s.ay))
                    anchors.append((s.bx, s.by))
            for s in ctx.arcs_by_layer.get(lyr, ()):
                if s.net_code == net_code:
                    anchors.append((s.ax, s.ay))
                    anchors.append((s.bx, s.by))

            chains = extract_chains(net_segs, anchors, snap_tol=SNAP_TOL_MM)
            cap = max_tuned_reduction_mm if net_name in tuned else None

            for pts, widths, gidxs in chains:
                old_len = _polyline_len(pts)
                old_n = len(gidxs)
                segs_before += old_n
                len_before += old_len

                if old_n < 2:
                    segs_after += old_n
                    len_after += old_len
                    continue

                new_pts, new_widths, did_change = smooth_chain(
                    pts, widths, gidxs, ctx, lyr, net_code, net_name, l_segs,
                    max_len_reduction_mm=cap,
                )
                if not did_change:
                    segs_after += old_n
                    len_after += old_len
                    continue

                # Replace original KiCad PCB_TRACK objects with the smoothed octilinear segments
                net_obj = board.FindNet(net_code)
                for idx_old in gidxs:
                    trk = l_tracks[idx_old]
                    _DETACHED.append(trk)
                    board.Remove(trk)
                for k in range(len(new_pts) - 1):
                    seg_new = pcbnew.PCB_TRACK(board)
                    seg_new.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(new_pts[k][0]), pcbnew.FromMM(new_pts[k][1])))
                    seg_new.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(new_pts[k + 1][0]), pcbnew.FromMM(new_pts[k + 1][1])))
                    seg_new.SetWidth(pcbnew.FromMM(new_widths[k]))
                    seg_new.SetLayer(lyr)
                    board.Add(seg_new)
                    seg_new.SetNet(net_obj)

                new_n = len(new_pts) - 1
                segs_after += new_n
                len_after += _polyline_len(new_pts)
                chains_smoothed += 1

    return {
        "chains_smoothed": chains_smoothed,
        "segs_before": segs_before,
        "segs_after": segs_after,
        "segs_removed": segs_before - segs_after,
        "len_before_mm": round(len_before, 2),
        "len_after_mm": round(len_after, 2),
        "len_saved_mm": round(len_before - len_after, 2),
    }


def smooth_board(
    board: pcbnew.BOARD,
    plan: dict | None = None,
    *,
    tuned_nets: set[str] | None = None,
    max_tuned_reduction_mm: float = TUNED_MAX_REDUCTION_MM,
    max_board_passes: int = 4,
) -> dict[str, float]:
    """Run DRC-safe octilinear track smoothing to a board-wide fixed point across
    all non-pour nets and copper layers of `board`. Returns aggregate stats."""
    first = _smooth_board_once(board, plan, tuned_nets=tuned_nets, max_tuned_reduction_mm=max_tuned_reduction_mm)
    total_chains = first["chains_smoothed"]
    segs_before = first["segs_before"]
    len_before = first["len_before_mm"]
    last = first
    for _ in range(max_board_passes - 1):
        if last["chains_smoothed"] == 0:
            break
        last = _smooth_board_once(board, plan, tuned_nets=tuned_nets, max_tuned_reduction_mm=max_tuned_reduction_mm)
        total_chains += last["chains_smoothed"]
    return {
        "chains_smoothed": total_chains,
        "segs_before": segs_before,
        "segs_after": last["segs_after"],
        "segs_removed": segs_before - last["segs_after"],
        "len_before_mm": round(len_before, 2),
        "len_after_mm": round(last["len_after_mm"], 2),
        "len_saved_mm": round(len_before - last["len_after_mm"], 2),
    }
