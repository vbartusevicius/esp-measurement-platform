"""Deterministic two-stage Google OR-Tools CP-SAT PCB placer.

Stage 1 fixes mechanical anchors (`locked: true` in `layout_<board>.yaml`) and
keepouts, then solves all active ICs, magnetics, discrete semiconductors and
fuses simultaneously with `AddNoOverlap2D` on `F.Cu`, `B.Cu`, 3D height
keepouts and cross-face `F<->B` drill/escape shadows, minimizing weighted L1
pad-to-pad Manhattan wirelength (`AddAbsEquality`) with a fixed seed and single
search worker.

Stage 2 freezes Stage 1 footprints with routing-escape halos and solves 2-pin
passives (`R`, `C`) in logical batches using a boolean `is_vert` variable
(`0/90` width/height swap via `OnlyEnforceIf`) anchored to the rotated pad
coordinates of their parent components, down-weighting global ground/power nets
so decoupling and filter passives hug their target pins.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import pcbnew
from ortools.sat.python import cp_model
from shapely.geometry import Polygon, box as sbox
from shapely.ops import unary_union

GRID_MM = 0.05
SEED = 42
STAGE1_SECONDS = 30.0
STAGE2_SECONDS = 10.0
GLOBAL_POWER = {"+3V3", "+5V", "+5V_S", "+24V_LOOP"}
HIGH_PRIORITY_PREFIXES = ("BUCK5_SW", "N$", "Net-", "OLED_C", "OLED_IREF", "OLED_RES", "SENSE_IN", "MA_SHUNT")


def g_floor(mm: float) -> int:
    return math.floor((mm - 1e-6) / GRID_MM)


def g_ceil(mm: float) -> int:
    return math.ceil((mm + 1e-6) / GRID_MM)


def g_round(mm: float) -> int:
    return round(mm / GRID_MM)


@dataclass
class OrientGeom:
    rot: int
    dx0: int
    dy0: int
    dx1: int
    dy1: int
    s1_extra: int
    pads: dict[str, tuple[int, int]]  # pad_key -> (dx_grid, dy_grid)


@dataclass
class PartSpec:
    ref: str
    fp: pcbnew.FOOTPRINT
    side: str          # "front" | "back"
    block: str
    value: str
    fpid: str
    height: float
    locked: bool
    is_passive: bool
    orients: dict[int, OrientGeom]


def _set_side(fp: pcbnew.FOOTPRINT, back: bool) -> None:
    if fp.IsFlipped() != back:
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)


def _body_and_pad_mm(fp: pcbnew.FOOTPRINT) -> tuple[float, float, float, float]:
    fp.BuildCourtyardCaches()
    back = fp.IsFlipped()
    bb = fp.GetCourtyard(pcbnew.B_CrtYd if back else pcbnew.F_CrtYd).BBox()
    fab = pcbnew.B_Fab if back else pcbnew.F_Fab
    for item in fp.GraphicalItems():
        if item.GetLayer() == fab and item.Type() == pcbnew.PCB_SHAPE_T:
            bb.Merge(item.GetBoundingBox())
    cu = pcbnew.B_Cu if back else pcbnew.F_Cu
    for pad in fp.Pads():
        if pad.IsOnLayer(cu):
            pbb = pad.GetBoundingBox()
            pbb.Inflate(pcbnew.FromMM(0.12))
            bb.Merge(pbb)
    return (
        pcbnew.ToMM(bb.GetLeft()),
        -pcbnew.ToMM(bb.GetBottom()),
        pcbnew.ToMM(bb.GetRight()),
        -pcbnew.ToMM(bb.GetTop()),
    )


def _halo_mm(fpid: str, is_passive: bool, spacious: bool) -> float:
    if is_passive:
        return 0.28 if spacious else 0.18
    if any(k in fpid for k in ("TSOT-23-6", "SOT-23-6", "SOT-23-5", "FPC_", "OLED_FPC")):
        return 0.50
    if any(k in fpid for k in ("SOT-23", "D_SMA", "D_SOD", "SWPA", "Fuse_")):
        return 0.32 if spacious else 0.30
    return 0.35


def _is_two_pin_passive(fp: pcbnew.FOOTPRINT, ref: str, fpid: str) -> bool:
    if not (ref.startswith(("R", "C", "FB")) and not ref.startswith("RV")):
        return False
    if fpid.startswith(("CP_", "C_Polarized", "C_Tantalum", "C_Elec")):
        return False
    if not fpid.startswith(("R_", "C_", "L_")):
        return False
    numbered = {p.GetNumber() for p in fp.Pads() if p.GetNumber()}
    return numbered == {"1", "2"}


def is_symmetric_two_pin_passive(fp: pcbnew.FOOTPRINT) -> bool:
    """True for unlocked symmetric 2-pin passives (`R`, non-polarized `C`, `L`, `FB`, `F`)
    whose 180-deg rotation preserves the identical courtyard while swapping Pad 1 <-> Pad 2.
    Excludes polarized capacitors (`CP_*`), diodes (`D*`), and locked anchors."""
    if fp.IsLocked():
        return False
    ref = fp.GetReference()
    if ref.startswith(("D", "RV", "SW", "J", "U", "Q", "K")):
        return False
    fpid = str(fp.GetFPID().GetLibItemName())
    if fpid.startswith(("CP_", "C_Polarized", "C_Tantalum", "C_Elec", "D_", "LED_")):
        return False
    if not (ref.startswith(("R", "C", "L", "FB", "F")) or fpid.startswith(("R_", "C_", "L_", "Fuse_"))):
        return False
    numbered = {p.GetNumber() for p in fp.Pads() if p.GetNumber()}
    if numbered != {"1", "2"}:
        return False
    # Verify pad symmetry about footprint origin (within 0.05 mm) so 180-deg flip has identical courtyard
    p1 = next(p for p in fp.Pads() if p.GetNumber() == "1").GetPosition()
    p2 = next(p for p in fp.Pads() if p.GetNumber() == "2").GetPosition()
    org = fp.GetPosition()
    return (
        abs((pcbnew.ToMM(p1.x - org.x) + pcbnew.ToMM(p2.x - org.x))) <= 0.05
        and abs((pcbnew.ToMM(p1.y - org.y) + pcbnew.ToMM(p2.y - org.y))) <= 0.05
    )


def _measure_part(
    fp: pcbnew.FOOTPRINT,
    side: str,
    block: str,
    height: float,
    locked: bool,
    rots: tuple[int, ...],
    spacious: bool,
) -> PartSpec:
    ref = fp.GetReference()
    fpid = str(fp.GetFPID().GetLibItemName())
    is_passive = not locked and _is_two_pin_passive(fp, ref, fpid)
    halo = 0.25 if locked else _halo_mm(fpid, is_passive, spacious)
    # Reserve an immediate moat around unlocked regulator/comparator ICs during Stage 1
    # so Stage-2 HF input/bootstrap caps & FB dividers land within ~3.5-5 mm of the IC pins.
    s1_extra_mm = (1.85 if spacious else 0.55) if (not locked and ref.startswith("U")) else 0.0
    s1_extra_grid = g_ceil(s1_extra_mm) if s1_extra_mm > 0 else 0

    orig_pos = fp.GetPosition()
    orig_rot = fp.GetOrientation().AsDegrees()
    orig_back = fp.IsFlipped()

    _set_side(fp, side == "back")
    fp.SetPosition(pcbnew.VECTOR2I(0, 0))
    orients: dict[int, OrientGeom] = {}
    for rot in rots:
        fp.SetOrientationDegrees(rot)
        x0, y0, x1, y1 = _body_and_pad_mm(fp)
        pad_pts: dict[str, list[tuple[float, float]]] = {}
        for pad in fp.Pads():
            net = pad.GetNetname()
            num = pad.GetNumber()
            if not net or not num:
                continue
            key = f"{num}:{net}"
            p = pad.GetPosition()
            pad_pts.setdefault(key, []).append((pcbnew.ToMM(p.x), -pcbnew.ToMM(p.y)))
        pads_grid = {
            k: (g_round(sum(pt[0] for pt in pts) / len(pts)),
                g_round(sum(pt[1] for pt in pts) / len(pts)))
            for k, pts in pad_pts.items()
        }
        # Extra fanout corridor in front of fine-pitch FFC / OLED FPC signal rows
        ex0, ey0, ex1, ey1 = x0 - halo, y0 - halo, x1 + halo, y1 + halo
        if locked and ("FPC_" in fpid or "OLED_FPC" in fpid) and pads_grid:
            avg_px = sum(v[0] for v in pads_grid.values()) / len(pads_grid) * GRID_MM
            avg_py = sum(v[1] for v in pads_grid.values()) / len(pads_grid) * GRID_MM
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if abs(avg_px - cx) > abs(avg_py - cy):
                if avg_px > cx:
                    ex1 = max(ex1, avg_px + 1.3)
                else:
                    ex0 = min(ex0, avg_px - 1.3)
            else:
                if avg_py > cy:
                    ey1 = max(ey1, avg_py + 1.3)
                else:
                    ey0 = min(ey0, avg_py - 1.3)
        orients[rot] = OrientGeom(
            rot=rot,
            dx0=g_floor(ex0),
            dy0=g_floor(ey0),
            dx1=g_ceil(ex1),
            dy1=g_ceil(ey1),
            s1_extra=s1_extra_grid,
            pads=pads_grid,
        )

    _set_side(fp, orig_back)
    fp.SetOrientationDegrees(orig_rot)
    fp.SetPosition(orig_pos)
    return PartSpec(
        ref=ref,
        fp=fp,
        side=side,
        block=block,
        value=fp.GetValue(),
        fpid=fpid,
        height=height,
        locked=locked,
        is_passive=is_passive,
        orients=orients,
    )


def _rect_box(x0: float, y0: float, x1: float, y1: float) -> tuple[int, int, int, int]:
    return g_floor(min(x0, x1)), g_floor(min(y0, y1)), g_ceil(max(x0, x1)), g_ceil(max(y0, y1))


def _outline_cutout_boxes(frame: dict, w: float, h: float) -> list[tuple[int, int, int, int]]:
    if "outline" not in frame:
        return []
    poly = Polygon([tuple(p) for p in frame["outline"]])
    diff = sbox(0.0, 0.0, w, h).difference(poly)
    if diff.is_empty:
        return []
    geoms = list(diff.geoms) if hasattr(diff, "geoms") else [diff]
    boxes = []
    for g in geoms:
        bx0, by0, bx1, by1 = g.bounds
        boxes.append(_rect_box(bx0 - 0.3, by0 - 0.3, bx1 + 0.3, by1 + 0.3))
    return boxes


def _selv_complement_boxes(frame: dict, w: float, h: float) -> list[tuple[int, int, int, int]]:
    regions = frame.get("domain_regions", {})
    if len(regions) <= 1 or "SELV" not in regions:
        return []
    selv = regions["SELV"]
    areas = selv if isinstance(selv, list) else [selv]
    allowed = None
    for r in areas:
        rb = sbox(r["x0"], r["y0"], r["x1"], r["y1"])
        allowed = rb if allowed is None else allowed.union(rb)
    diff = sbox(0.0, 0.0, w, h).difference(allowed)
    if diff.is_empty:
        return []
    geoms = list(diff.geoms) if hasattr(diff, "geoms") else [diff]
    return [_rect_box(g.bounds[0] - 0.25, g.bounds[1] - 0.25, g.bounds[2] + 0.25, g.bounds[3] + 0.25) for g in geoms]


def _anchor_obstacles(
    board: pcbnew.BOARD,
    plan: dict,
    anchors: dict[str, PartSpec],
) -> tuple[dict[str, list[tuple[int, int, int, int]]], list[tuple[tuple[int, int, int, int], float]]]:
    """Return fixed 2D keepout boxes per side ('front', 'back') and 3D height-limited
    regions `(box_grid, max_height_mm)` under raised socketed modules."""
    frame = plan["frame"]
    w, h = frame["size"]["x"], frame["size"]["y"]
    obs: dict[str, list[tuple[int, int, int, int]]] = {"front": [], "back": []}
    height_caps: list[tuple[tuple[int, int, int, int], float]] = []

    for b in _outline_cutout_boxes(frame, w, h) + _selv_complement_boxes(frame, w, h):
        obs["front"].append(b)
        obs["back"].append(b)

    for slot in frame.get("slots", []):
        b = _rect_box(slot["x0"] - 0.5, slot["y0"] - 0.5, slot["x1"] + 0.5, slot["y1"] + 0.5)
        obs["front"].append(b)
        obs["back"].append(b)

    for ko in frame.get("copper_keepout", []):
        b = _rect_box(ko["x0"] - 0.25, ko["y0"] - 0.25, ko["x1"] + 0.25, ko["y1"] + 0.25)
        obs["front"].append(b)
        obs["back"].append(b)

    case = plan.get("case", {})
    for kind, side, half in (("legs", "back", 2.5), ("pegs", "front", 1.5), ("standoffs", "front", 1.5)):
        for pt in case.get(kind, []):
            obs[side].append(_rect_box(pt["x"] - half, pt["y"] - half, pt["x"] + half, pt["y"] + half))

    for ko in plan.get("placement", {}).get("keepouts", []):
        b = _rect_box(ko["x0"], ko["y0"], ko["x1"], ko["y1"])
        target = ko.get("side", "both")
        if target in ("front", "both"):
            obs["front"].append(b)
        if target in ("back", "both"):
            obs["back"].append(b)

    raised_refs = set(frame.get("raised_modules", []))
    for ref, spec in anchors.items():
        fp = spec.fp
        px = g_round(pcbnew.ToMM(fp.GetPosition().x))
        py = g_round(-pcbnew.ToMM(fp.GetPosition().y))
        og = next(iter(spec.orients.values()))
        full_box = (px + og.dx0, py + og.dy0, px + og.dx1, py + og.dy1)
        opp_side = "back" if spec.side == "front" else "front"

        if ref in raised_refs:
            # Raised module on 5 mm female sockets: allow low-profile SMD parts underneath
            # (`height <= 3.8 mm`), while blocking the THT socket strips + pin escape corridors
            # on both F.Cu and B.Cu.
            height_caps.append((full_box, 3.8))
            tht_pts = [
                (pcbnew.ToMM(pad.GetPosition().x), -pcbnew.ToMM(pad.GetPosition().y))
                for pad in fp.Pads() if pad.GetDrillSizeX() > 0
            ]
            # Group into colinear pin strips (along x or along y)
            xs = sorted({round(p[0], 2) for p in tht_pts})
            ys = sorted({round(p[1], 2) for p in tht_pts})
            if len(ys) <= len(xs):
                for y_row in ys:
                    row_xs = [p[0] for p in tht_pts if abs(p[1] - y_row) < 0.2]
                    sb = _rect_box(min(row_xs) - 1.5, y_row - 1.9, max(row_xs) + 1.5, y_row + 1.9)
                    obs["front"].append(sb)
                    obs["back"].append(sb)
            else:
                for x_col in xs:
                    col_ys = [p[1] for p in tht_pts if abs(p[0] - x_col) < 0.2]
                    sb = _rect_box(x_col - 1.9, min(col_ys) - 1.5, x_col + 1.9, max(col_ys) + 1.5)
                    obs["front"].append(sb)
                    obs["back"].append(sb)
            continue

        obs[spec.side].append(full_box)

        # Cross-face F<->B keepouts: THT drills/annular rings & NPTH clip holes block opposite face
        for pad in fp.Pads():
            if pad.GetDrillSizeX() > 0:
                pbb = pad.GetBoundingBox()
                obs[opp_side].append(_rect_box(
                    pcbnew.ToMM(pbb.GetLeft()) - 0.45,
                    -pcbnew.ToMM(pbb.GetBottom()) - 0.45,
                    pcbnew.ToMM(pbb.GetRight()) + 0.45,
                    -pcbnew.ToMM(pbb.GetTop()) + 0.45,
                ))
        # Fine-pitch FFC / FPC via-escape shadow on opposite face
        if "FPC_" in spec.fpid or "OLED_FPC" in spec.fpid:
            sig_pads = [pad.GetBoundingBox() for pad in fp.Pads() if pad.GetNetname()]
            if sig_pads:
                obs[opp_side].append(_rect_box(
                    min(pcbnew.ToMM(b.GetLeft()) for b in sig_pads) - 0.35,
                    min(-pcbnew.ToMM(b.GetBottom()) for b in sig_pads) - 0.35,
                    max(pcbnew.ToMM(b.GetRight()) for b in sig_pads) + 0.35,
                    max(-pcbnew.ToMM(b.GetTop()) for b in sig_pads) + 0.35,
                ))

    return obs, height_caps


def _net_weight(net: str) -> int:
    if net in ("VIN_RAW", "VIN_FUSED", "+5V_IN"):
        return 48
    if net == "BUCK5_SW":
        return 45
    if net.endswith("_TERM"):
        return 38
    if any(net.startswith(p) for p in HIGH_PRIORITY_PREFIXES):
        return 26
    return 12


def _cap_farads_approx(val: str) -> float:
    tok = val.strip().split()[0]
    for unit, scale in (("p", 1e-12), ("n", 1e-9), ("u", 1e-6), ("µ", 1e-6)):
        if unit in tok:
            left, right = tok.split(unit, 1)
            right_digits = "".join(ch for ch in right if ch.isdigit())
            num = float(f"{left}.{right_digits}" if right_digits else left)
            return num * scale
    return 1.0


def _ref_sort_key(ref: str) -> tuple[str, int]:
    prefix = ref.rstrip("0123456789")
    num = ref[len(prefix):]
    return prefix, int(num) if num else 0


def _build_pad_edges(
    parts: dict[str, PartSpec],
    solving_refs: set[str],
    placed_coords: dict[str, tuple[int, int, int]],
) -> list[tuple[tuple[str, str], tuple[str, str], int]]:
    """Build weighted pad-to-pad L1 edges `(pad_a, pad_b, weight)` touching `solving_refs`.
    Each pad endpoint is `(ref, pad_key)` where `ref` is either in `solving_refs` or `placed_coords`."""
    active_refs = solving_refs | set(placed_coords)
    by_net: dict[str, list[tuple[str, str]]] = {}
    for ref in sorted(active_refs, key=_ref_sort_key):
        spec = parts[ref]
        sample_og = next(iter(spec.orients.values()))
        # Deduplicate multi-pad poles on the same component & net (keep first pad_key)
        seen_nets: set[str] = set()
        for pkey in sorted(sample_og.pads):
            net = pkey.split(":", 1)[1]
            if net in seen_nets:
                continue
            seen_nets.add(net)
            by_net.setdefault(net, []).append((ref, pkey))

    edges: list[tuple[tuple[str, str], tuple[str, str], int]] = []

    # 1. Local / signal / switching nets (everything except GND and shared multi-drop rails)
    for net, endpoints in sorted(by_net.items()):
        if net == "GND" or net in GLOBAL_POWER or len(endpoints) < 2:
            continue
        if not any(r in solving_refs for r, _ in endpoints):
            continue
        w = _net_weight(net)
        fixed_eps = [ep for ep in endpoints if ep[0] in placed_coords]
        mov_eps = [ep for ep in endpoints if ep[0] in solving_refs]
        if len(endpoints) <= 5:
            for i, a in enumerate(endpoints):
                for b in endpoints[i + 1:]:
                    if a[0] in solving_refs or b[0] in solving_refs:
                        edges.append((a, b, w))
        else:
            # Connect every movable endpoint to fixed endpoints + chain movable endpoints
            for m in mov_eps:
                for f in fixed_eps:
                    edges.append((m, f, w))
            for i in range(len(mov_eps) - 1):
                edges.append((mov_eps[i], mov_eps[i + 1], max(4, w // 2)))

    # 2. Shared power rails (+3V3, +5V, +5V_S, +24V_LOOP) & GND: anchor passives and
    #    co-block discretes directly to their parent active/anchor pins in the same block.
    paired_caps: set[str] = set()
    handled_power_entry: set[tuple[str, str]] = set()

    # 2a. Power-entry surge/reverse-protection chain (`pwr_in` / `power`): keep TVS + reverse
    #     diode tightly looped at the input power connector (J1) instead of drifting into the board.
    entry_conns = [
        r for r in sorted(placed_coords, key=_ref_sort_key)
        if parts[r].locked and any(
            pk.split(":", 1)[1] in ("VIN_RAW", "+5V_IN")
            for pk in next(iter(parts[r].orients.values())).pads
        )
    ]
    if entry_conns:
        j_in = entry_conns[0]
        j_gnd_pks = [
            pk for pk in sorted(next(iter(parts[j_in].orients.values())).pads)
            if pk.split(":", 1)[1] == "GND"
        ]
        pwr_diodes = [
            r for r in sorted(solving_refs, key=_ref_sort_key)
            if parts[r].block in ("pwr_in", "power") and not parts[r].is_passive and r.startswith("D")
        ]
        j_vin_pks = [
            pk for pk in sorted(next(iter(parts[j_in].orients.values())).pads)
            if pk.split(":", 1)[1] in ("VIN_RAW", "+5V_IN")
        ]
        # Connect co-block power-entry diodes on +24V_LOOP / +5V_S directly to each other
        # and break L1 triangle-inequality plateaus by pulling D2 directly toward J1 as well.
        for i, da in enumerate(pwr_diodes):
            pks_a = sorted(next(iter(parts[da].orients.values())).pads)
            for db in pwr_diodes[i + 1:]:
                pks_b = sorted(next(iter(parts[db].orients.values())).pads)
                for pka in pks_a:
                    for pkb in pks_b:
                        rail = pka.split(":", 1)[1]
                        if rail == pkb.split(":", 1)[1] and rail in GLOBAL_POWER:
                            edges.append(((da, pka), (db, pkb), 40))
                            handled_power_entry.add((da, pka))
                            handled_power_entry.add((db, pkb))
            if j_gnd_pks:
                for pka in pks_a:
                    if pka.split(":", 1)[1] == "GND":
                        edges.append(((da, pka), (j_in, j_gnd_pks[0]), 38))
                        handled_power_entry.add((da, pka))
            if j_vin_pks:
                for pka in pks_a:
                    if pka.split(":", 1)[1] == "VIN_FUSED":
                        edges.append(((da, pka), (j_in, j_vin_pks[0]), 22))

    blocks = sorted({parts[r].block for r in solving_refs})
    for blk in blocks:
        blk_solving = [r for r in sorted(solving_refs, key=_ref_sort_key) if parts[r].block == blk]
        blk_fixed = [r for r in sorted(placed_coords, key=_ref_sort_key) if parts[r].block == blk]

        # Identify pure decoupling caps in this block: 2-pin C between a rail in GLOBAL_POWER and GND
        for rail in sorted(GLOBAL_POWER):
            rail_targets = [
                (r, pkey) for r in blk_fixed
                for pkey in sorted(next(iter(parts[r].orients.values())).pads)
                if pkey.split(":", 1)[1] == rail and not parts[r].is_passive
            ]
            if not rail_targets:
                continue
            dec_caps = []
            for r in blk_solving:
                if not (parts[r].is_passive and r.startswith("C")):
                    continue
                pkeys = sorted(next(iter(parts[r].orients.values())).pads)
                nets = {pk.split(":", 1)[1] for pk in pkeys}
                if nets == {rail, "GND"}:
                    dec_caps.append(r)
            if dec_caps:
                # Single-target regulator blocks (e.g. buck5v U1.VIN / L1.+5V): sort smallest HF
                # ceramic cap (100n) FIRST with highest weight so HF cap hugs the IC pin;
                # prefer the target's OWN local GND pin over distant GND pins so caps never flip 180 deg!
                if len(rail_targets) == 1:
                    tgt_ref, tgt_rail_pk = rail_targets[0]
                    tgt_own_gnd = [
                        (tgt_ref, pk)
                        for pk in sorted(next(iter(parts[tgt_ref].orients.values())).pads)
                        if pk.split(":", 1)[1] == "GND"
                    ]
                    gnd_targets = tgt_own_gnd or [
                        (r, pk) for r in blk_fixed if not parts[r].is_passive
                        for pk in sorted(next(iter(parts[r].orients.values())).pads)
                        if pk.split(":", 1)[1] == "GND"
                    ]
                    ordered_caps = sorted(dec_caps, key=lambda r: (_cap_farads_approx(parts[r].value), _ref_sort_key(r)))
                    for idx, cap_ref in enumerate(ordered_caps):
                        is_hf = _cap_farads_approx(parts[cap_ref].value) <= 150e-9
                        w_rail = 38 if is_hf else max(16, 26 - 4 * idx)
                        w_gnd = 28 if is_hf else 18
                        cap_pks = sorted(next(iter(parts[cap_ref].orients.values())).pads)
                        cap_rail_pk = next(pk for pk in cap_pks if pk.split(":", 1)[1] == rail)
                        cap_gnd_pk = next(pk for pk in cap_pks if pk.split(":", 1)[1] == "GND")
                        edges.append(((cap_ref, cap_rail_pk), (tgt_ref, tgt_rail_pk), w_rail))
                        for g_ref, g_pk in gnd_targets:
                            edges.append(((cap_ref, cap_gnd_pk), (g_ref, g_pk), w_gnd))
                        paired_caps.add(cap_ref)
                else:
                    ordered_caps = sorted(dec_caps, key=lambda r: (-_cap_farads_approx(parts[r].value), _ref_sort_key(r)))
                    for idx, cap_ref in enumerate(ordered_caps):
                        tgt_ref, tgt_rail_pk = rail_targets[min(idx, len(rail_targets) - 1)]
                        cap_pks = sorted(next(iter(parts[cap_ref].orients.values())).pads)
                        cap_rail_pk = next(pk for pk in cap_pks if pk.split(":", 1)[1] == rail)
                        cap_gnd_pk = next(pk for pk in cap_pks if pk.split(":", 1)[1] == "GND")
                        edges.append(((cap_ref, cap_rail_pk), (tgt_ref, tgt_rail_pk), 18))
                        tgt_gnd_pks = [
                            pk for pk in sorted(next(iter(parts[tgt_ref].orients.values())).pads)
                            if pk.split(":", 1)[1] == "GND"
                        ]
                        if tgt_gnd_pks:
                            edges.append(((cap_ref, cap_gnd_pk), (tgt_ref, tgt_gnd_pks[0]), 8))
                        paired_caps.add(cap_ref)

    # 2b. Shared-parent pin attraction (Stage 2): whenever a 2-pin passive bridges two
    #     nets that both appear on a single already-placed non-passive footprint (e.g. an
    #     IC/regulator's VCC+GND, BST+SW, FB+GND, EN+GND, or clamp signal+GND), pull each
    #     passive pad directly to its matching pin on that parent footprint rather than
    #     a global ground centroid or global bounding-box HPWL.
    shared_parent_handled: set[str] = set()
    for ref in sorted(solving_refs, key=_ref_sort_key):
        spec = parts[ref]
        if not spec.is_passive or ref in paired_caps:
            continue
        pks = sorted(next(iter(spec.orients.values())).pads)
        if len(pks) != 2:
            continue
        pk1, pk2 = pks[0], pks[1]
        n1, n2 = pk1.split(":", 1)[1], pk2.split(":", 1)[1]
        if not n1 or not n2 or n1 == n2:
            continue

        # Find already-placed non-passive footprints that carry BOTH n1 and n2
        parent_cands = []
        for pref in sorted(placed_coords, key=_ref_sort_key):
            pspec = parts[pref]
            if pspec.is_passive:
                continue
            p_px, p_py, p_rot = placed_coords[pref]
            pog = pspec.orients[p_rot]
            p1_list = [(pk, p_px + dx, p_py + dy) for pk, (dx, dy) in sorted(pog.pads.items()) if pk.split(":", 1)[1] == n1]
            p2_list = [(pk, p_px + dx, p_py + dy) for pk, (dx, dy) in sorted(pog.pads.items()) if pk.split(":", 1)[1] == n2]
            if not p1_list or not p2_list:
                continue
            # Closest pin pair on this parent footprint
            best_pair = min(
                ((abs(x1 - x2) + abs(y1 - y2), pk_a, pk_b)
                 for pk_a, x1, y1 in p1_list for pk_b, x2, y2 in p2_list),
                key=lambda item: item[0],
            )
            same_blk = 0 if pspec.block == spec.block else 1
            is_conn = 1 if pref.startswith("J") else 0
            parent_cands.append((same_blk, is_conn, best_pair[0], pref, best_pair[1], best_pair[2]))

        if not parent_cands:
            continue
        _, _, _pair_d, best_pref, t1_pk, t2_pk = min(parent_cands)
        is_hf_cap = ref.startswith("C") and _cap_farads_approx(spec.value) <= 150e-9
        w_p = 36 if is_hf_cap else 24
        edges.append(((ref, pk1), (best_pref, t1_pk), w_p))
        edges.append(((ref, pk2), (best_pref, t2_pk), w_p))
        shared_parent_handled.add(ref)

    for rail in sorted(GLOBAL_POWER | {"GND"}):
        is_gnd = rail == "GND"
        base_w = 2 if is_gnd else 8
        endpoints = by_net.get(rail, [])
        if len(endpoints) < 2:
            continue
        for ref, pkey in endpoints:
            if (ref not in solving_refs or ref in paired_caps
                    or ref in shared_parent_handled or (ref, pkey) in handled_power_entry):
                continue
            blk = parts[ref].block
            same_blk_fixed = [
                (r, pk) for r, pk in endpoints
                if r in placed_coords and parts[r].block == blk and not parts[r].is_passive
            ]
            same_blk_mov = [
                (r, pk) for r, pk in endpoints
                if r in solving_refs and r != ref and parts[r].block == blk and not parts[r].is_passive
            ]
            if same_blk_fixed:
                for tgt in same_blk_fixed:
                    edges.append(((ref, pkey), tgt, base_w))
            elif same_blk_mov:
                for tgt in same_blk_mov:
                    if _ref_sort_key(ref) < _ref_sort_key(tgt[0]):
                        edges.append(((ref, pkey), tgt, base_w))
            elif not is_gnd:
                sources = [(r, pk) for r, pk in endpoints if r in placed_coords and not parts[r].is_passive]
                for tgt in sources[:3]:
                    edges.append(((ref, pkey), tgt, 2))

    # 3. Stage-1 passive lookahead: when 2-pin series passives (R/C not on GND) are not
    #    yet placed, bridge their two nets so Stage-1 clamps/fuses/ICs sit directly between
    #    their connector poles and MCU/regulator pins (biasing toward field terminals).
    unplaced_passives = [
        r for r, sp in sorted(parts.items(), key=lambda kv: _ref_sort_key(kv[0]))
        if sp.is_passive and r not in active_refs
    ]
    for r in unplaced_passives:
        pkeys = sorted(next(iter(parts[r].orients.values())).pads)
        nets = [pk.split(":", 1)[1] for pk in pkeys]
        if len(nets) != 2 or "GND" in nets or nets[0] == nets[1]:
            continue
        na, nb = nets
        if na in GLOBAL_POWER and nb in GLOBAL_POWER:
            continue
        eps_a = by_net.get(na, [])
        eps_b = by_net.get(nb, [])
        if not eps_a or not eps_b or len(eps_a) * len(eps_b) > 12:
            continue
        w_la = 18 if (na.endswith("_TERM") or nb.endswith("_TERM")) else 8
        for ea in eps_a:
            for eb in eps_b:
                if ea[0] != eb[0] and (ea[0] in solving_refs or eb[0] in solving_refs):
                    edges.append((ea, eb, w_la))

    return edges


def _disjoint_boxes(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """Decompose an arbitrary union of axis-aligned integer rectangles into
    mutually non-overlapping rectangles so `AddNoOverlap2D` never sees two fixed
    keepouts overlapping each other."""
    valid = [(x0, y0, x1, y1) for x0, y0, x1, y1 in boxes if x1 > x0 and y1 > y0]
    if not valid:
        return []
    merged = unary_union([sbox(x0, y0, x1, y1) for x0, y0, x1, y1 in valid])
    xs = sorted({x for x0, _, x1, _ in valid for x in (x0, x1)})
    out: list[tuple[int, int, int, int]] = []
    ymin_all = min(b[1] for b in valid) - 1
    ymax_all = max(b[3] for b in valid) + 1
    for xa, xb in zip(xs, xs[1:]):
        if xb <= xa:
            continue
        piece = merged.intersection(sbox(xa, ymin_all, xb, ymax_all))
        if piece.is_empty:
            continue
        geoms = list(piece.geoms) if hasattr(piece, "geoms") else [piece]
        for g in geoms:
            if g.area < 0.5:
                continue
            gx0, gy0, gx1, gy1 = g.bounds
            ix0, iy0, ix1, iy1 = round(gx0), round(gy0), round(gx1), round(gy1)
            if ix1 > ix0 and iy1 > iy0:
                out.append((ix0, iy0, ix1, iy1))
    return out


def _solve_subset(
    parts: dict[str, PartSpec],
    solving_refs: list[str],
    placed_coords: dict[str, tuple[int, int, int]],
    fixed_obs: dict[str, list[tuple[int, int, int, int]]],
    height_caps: list[tuple[tuple[int, int, int, int], float]],
    board_w_grid: int,
    board_h_grid: int,
    edge_margin_grid: dict[str, tuple[int, int, int, int]],
    time_limit_s: float,
    stage_label: str,
) -> dict[str, tuple[int, int, int]]:
    if not solving_refs:
        return {}

    model = cp_model.CpModel()
    x_intervals: dict[str, list[cp_model.IntervalVar]] = {"front": [], "back": []}
    y_intervals: dict[str, list[cp_model.IntervalVar]] = {"front": [], "back": []}

    raw_fixed: dict[str, list[tuple[int, int, int, int]]] = {
        "front": list(fixed_obs["front"]),
        "back": list(fixed_obs["back"]),
    }
    for ref, (px, py, rot) in sorted(placed_coords.items(), key=lambda kv: _ref_sort_key(kv[0])):
        spec = parts[ref]
        if spec.locked:
            continue
        og = spec.orients[rot]
        raw_fixed[spec.side].append((px + og.dx0, py + og.dy0, px + og.dx1, py + og.dy1))

    for side in ("front", "back"):
        for idx, (bx0, by0, bx1, by1) in enumerate(_disjoint_boxes(raw_fixed[side])):
            x_intervals[side].append(model.NewFixedSizeIntervalVar(bx0, bx1 - bx0, f"fx_{side}_{idx}"))
            y_intervals[side].append(model.NewFixedSizeIntervalVar(by0, by1 - by0, f"fy_{side}_{idx}"))

    pos_vars: dict[str, tuple[cp_model.IntVar, cp_model.IntVar]] = {}
    orient_vars: dict[str, dict[int, cp_model.IntVar]] = {}
    pad_vars: dict[tuple[str, str], tuple[cp_model.IntVar, cp_model.IntVar]] = {}

    is_stage1 = "stage1" in stage_label

    for ref in sorted(solving_refs, key=_ref_sort_key):
        spec = parts[ref]
        mx0, my0, mx1, my1 = edge_margin_grid[spec.side]

        px = model.NewIntVar(0, board_w_grid, f"x_{ref}")
        py = model.NewIntVar(0, board_h_grid, f"y_{ref}")
        pos_vars[ref] = (px, py)

        o_bools = {rot: model.NewBoolVar(f"o_{ref}_{rot}") for rot in sorted(spec.orients)}
        model.AddExactlyOne(list(o_bools.values()))
        orient_vars[ref] = o_bools

        bx0 = model.NewIntVar(mx0, board_w_grid - mx1, f"bx0_{ref}")
        bx1 = model.NewIntVar(mx0, board_w_grid - mx1, f"bx1_{ref}")
        bw = model.NewIntVar(1, board_w_grid, f"bw_{ref}")
        by0 = model.NewIntVar(my0, board_h_grid - my1, f"by0_{ref}")
        by1 = model.NewIntVar(my0, board_h_grid - my1, f"by1_{ref}")
        bh = model.NewIntVar(1, board_h_grid, f"bh_{ref}")

        if spec.is_passive and set(spec.orients) == {0, 90, 180, 270}:
            # Stage 2 boolean `is_vert` variable (`0/90` width/height swap via `OnlyEnforceIf`)
            is_vert = model.NewBoolVar(f"vert_{ref}")
            model.AddBoolOr([o_bools[0], o_bools[180]]).OnlyEnforceIf(is_vert.Not())
            model.AddBoolOr([o_bools[90], o_bools[270]]).OnlyEnforceIf(is_vert)
            model.Add(o_bools[90] == 0).OnlyEnforceIf(is_vert.Not())
            model.Add(o_bools[270] == 0).OnlyEnforceIf(is_vert.Not())
            model.Add(o_bools[0] == 0).OnlyEnforceIf(is_vert)
            model.Add(o_bools[180] == 0).OnlyEnforceIf(is_vert)

            og_h, og_v = spec.orients[0], spec.orients[90]
            model.Add(bw == og_h.dx1 - og_h.dx0).OnlyEnforceIf(is_vert.Not())
            model.Add(bh == og_h.dy1 - og_h.dy0).OnlyEnforceIf(is_vert.Not())
            model.Add(bw == og_v.dx1 - og_v.dx0).OnlyEnforceIf(is_vert)
            model.Add(bh == og_v.dy1 - og_v.dy0).OnlyEnforceIf(is_vert)

        for rot, bvar in o_bools.items():
            og = spec.orients[rot]
            pad_m = og.s1_extra if is_stage1 else 0
            dx0_e, dx1_e = og.dx0 - pad_m, og.dx1 + pad_m
            dy0_e, dy1_e = og.dy0 - pad_m, og.dy1 + pad_m
            model.Add(bx0 == px + dx0_e).OnlyEnforceIf(bvar)
            model.Add(bx1 == px + dx1_e).OnlyEnforceIf(bvar)
            model.Add(bw == dx1_e - dx0_e).OnlyEnforceIf(bvar)
            model.Add(by0 == py + dy0_e).OnlyEnforceIf(bvar)
            model.Add(by1 == py + dy1_e).OnlyEnforceIf(bvar)
            model.Add(bh == dy1_e - dy0_e).OnlyEnforceIf(bvar)

        x_iv = model.NewIntervalVar(bx0, bw, bx1, f"xiv_{ref}")
        y_iv = model.NewIntervalVar(by0, bh, by1, f"yiv_{ref}")
        x_intervals[spec.side].append(x_iv)
        y_intervals[spec.side].append(y_iv)

        # 3D height keepout under raised modules if this part is too tall
        if spec.side == "front":
            for h_idx, ((hx0, hy0, hx1, hy1), max_h) in enumerate(height_caps):
                if spec.height > max_h:
                    sep = [model.NewBoolVar(f"hc_{ref}_{h_idx}_{d}") for d in range(4)]
                    model.AddBoolOr(sep)
                    model.Add(bx1 <= hx0).OnlyEnforceIf(sep[0])
                    model.Add(bx0 >= hx1).OnlyEnforceIf(sep[1])
                    model.Add(by1 <= hy0).OnlyEnforceIf(sep[2])
                    model.Add(by0 >= hy1).OnlyEnforceIf(sep[3])

        # Exact rotated pad coordinates
        sample_pads = next(iter(spec.orients.values())).pads
        for pkey in sorted(sample_pads):
            pad_x = model.NewIntVar(0, board_w_grid, f"px_{ref}_{pkey}")
            pad_y = model.NewIntVar(0, board_h_grid, f"py_{ref}_{pkey}")
            for rot, bvar in o_bools.items():
                dx, dy = spec.orients[rot].pads[pkey]
                model.Add(pad_x == px + dx).OnlyEnforceIf(bvar)
                model.Add(pad_y == py + dy).OnlyEnforceIf(bvar)
            pad_vars[(ref, pkey)] = (pad_x, pad_y)

    for side in ("front", "back"):
        if len(x_intervals[side]) > 1:
            model.AddNoOverlap2D(x_intervals[side], y_intervals[side])

    # Fixed pad lookup for already-placed components
    fixed_pads: dict[tuple[str, str], tuple[int, int]] = {}
    for ref, (px, py, rot) in placed_coords.items():
        og = parts[ref].orients[rot]
        for pkey, (dx, dy) in og.pads.items():
            fixed_pads[(ref, pkey)] = (px + dx, py + dy)

    edges = _build_pad_edges(parts, set(solving_refs), placed_coords)
    obj_terms = []
    max_span = board_w_grid + board_h_grid
    for idx, (pa, pb, weight) in enumerate(edges):
        ax, ay = pad_vars[pa] if pa in pad_vars else fixed_pads[pa]
        bx, by = pad_vars[pb] if pb in pad_vars else fixed_pads[pb]
        diff_x = model.NewIntVar(-max_span, max_span, f"dx_{idx}")
        diff_y = model.NewIntVar(-max_span, max_span, f"dy_{idx}")
        abs_x = model.NewIntVar(0, max_span, f"ax_{idx}")
        abs_y = model.NewIntVar(0, max_span, f"ay_{idx}")
        model.Add(diff_x == ax - bx)
        model.Add(diff_y == ay - by)
        model.AddAbsEquality(abs_x, diff_x)
        model.AddAbsEquality(abs_y, diff_y)
        obj_terms.append(weight * (abs_x + abs_y))

    if obj_terms:
        model.Minimize(sum(obj_terms))

    # Seed search hints on slotted/multi-domain boards so LNS starts in the right
    # topological bay (e.g. power-entry parts in the J1 bay rather than across slots).
    if is_stage1 and board_w_grid * GRID_MM >= 25.0:
        hint_acc: dict[str, list[tuple[int, int, int]]] = {}
        for pa, pb, w in edges:
            if pa[0] in pos_vars and pb in fixed_pads:
                hint_acc.setdefault(pa[0], []).append((*fixed_pads[pb], w))
            elif pb[0] in pos_vars and pa in fixed_pads:
                hint_acc.setdefault(pb[0], []).append((*fixed_pads[pa], w))
        for ref, pts in hint_acc.items():
            tw = sum(p[2] for p in pts)
            if tw > 0:
                hx = min(max(round(sum(p[0] * p[2] for p in pts) / tw), 0), board_w_grid)
                hy = min(max(round(sum(p[1] * p[2] for p in pts) / tw), 0), board_h_grid)
                model.AddHint(pos_vars[ref][0], hx)
                model.AddHint(pos_vars[ref][1], hy)

    solver = cp_model.CpSolver()
    solver.parameters.random_seed = SEED
    solver.parameters.num_search_workers = 1
    solver.parameters.max_deterministic_time = 15.0 if "stage1" in stage_label else 5.0
    solver.parameters.max_time_in_seconds = max(time_limit_s, 60.0)

    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"CP-SAT {stage_label} failed with status {solver.StatusName(status)}")

    solved: dict[str, tuple[int, int, int]] = {}
    for ref in solving_refs:
        px, py = pos_vars[ref]
        rot = next(r for r, bv in orient_vars[ref].items() if solver.Value(bv))
        solved[ref] = (solver.Value(px), solver.Value(py), rot)
    return solved


CROSSING_PENALTY_MM = 5.0


def _segs_properly_cross(
    a: tuple[float, float], b: tuple[float, float],
    c: tuple[float, float], d: tuple[float, float],
) -> bool:
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    eps = 1e-6
    return (
        abs(o1) > eps and abs(o2) > eps and abs(o3) > eps and abs(o4) > eps
        and (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)
    )


def _rotate_pt_180(pt: tuple[float, float], origin: tuple[float, float]) -> tuple[float, float]:
    return (2.0 * origin[0] - pt[0], 2.0 * origin[1] - pt[1])


def _boxes_clash(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def uncross_and_align_passives(
    board: pcbnew.BOARD,
    plan: dict | None = None,
    *,
    only_refs: set[str] | None = None,
) -> dict[str, int]:
    """Zero-courtyard post-placement 180-deg uncrossing & shared-parent pin-pair alignment.

    For every unlocked symmetric 2-pin passive (excluding polarized caps/diodes):
      1. Find each pad's nearest same-net pin on another footprint, strongly preferring
         a shared parent footprint carrying both nets.
      2. Score `rot` vs `(rot + 180) % 360` by `sum(dist(pad_k, target_k))` plus a
         crossing penalty when `(p1->t1)` intersects `(p2->t2)`, flipping 180 deg
         whenever cost strictly decreases (identical courtyard, zero overlap risk).
      3. When sitting beside an adjacent pin pair (`<= 4.0 mm` apart) on a shared parent,
         align the passive along the pin-pair midpoint if clash-free against all other
         footprints, board margins, and keepouts.
    """
    fps = {fp.GetReference(): fp for fp in board.Footprints()}

    def fp_pad_map() -> dict[str, dict[str, list[tuple[float, float]]]]:
        out: dict[str, dict[str, list[tuple[float, float]]]] = {}
        for ref, fp in fps.items():
            by_n: dict[str, list[tuple[float, float]]] = {}
            for pad in fp.Pads():
                n = pad.GetNetname()
                if n and pad.GetNumber():
                    p = pad.GetPosition()
                    by_n.setdefault(n, []).append((pcbnew.ToMM(p.x), -pcbnew.ToMM(p.y)))
            out[ref] = by_n
        return out

    # Collect fixed board/keepout obstacles in mm for clash-free pin-pair midpoint alignment
    fixed_mm: dict[str, list[tuple[float, float, float, float]]] = {"front": [], "back": []}
    bounds_mm: dict[str, tuple[float, float, float, float]] = {}
    raised_refs: set[str] = set()
    if plan:
        frame = plan["frame"]
        w_mm, h_mm = frame["size"]["x"], frame["size"]["y"]
        base_m = max(frame.get("edge_clearance", 0.3), 0.35)
        margins = plan.get("placement", {}).get("edge_margins", {})
        for side in ("front", "back"):
            sm = margins.get(side, {})
            bounds_mm[side] = (
                sm.get("x0", base_m), sm.get("y0", base_m),
                w_mm - sm.get("x1", base_m), h_mm - sm.get("y1", base_m),
            )
        raised_refs = set(frame.get("raised_modules", []))
        for b in _outline_cutout_boxes(frame, w_mm, h_mm) + _selv_complement_boxes(frame, w_mm, h_mm):
            bm = (b[0] * GRID_MM, b[1] * GRID_MM, b[2] * GRID_MM, b[3] * GRID_MM)
            fixed_mm["front"].append(bm)
            fixed_mm["back"].append(bm)
        for slot in frame.get("slots", []):
            bm = (slot["x0"] - 0.5, slot["y0"] - 0.5, slot["x1"] + 0.5, slot["y1"] + 0.5)
            fixed_mm["front"].append(bm)
            fixed_mm["back"].append(bm)
        for ko in frame.get("copper_keepout", []):
            bm = (ko["x0"] - 0.25, ko["y0"] - 0.25, ko["x1"] + 0.25, ko["y1"] + 0.25)
            fixed_mm["front"].append(bm)
            fixed_mm["back"].append(bm)
        for ko in plan.get("placement", {}).get("keepouts", []):
            bm = (ko["x0"], ko["y0"], ko["x1"], ko["y1"])
            target = ko.get("side", "both")
            if target in ("front", "both"):
                fixed_mm["front"].append(bm)
            if target in ("back", "both"):
                fixed_mm["back"].append(bm)
        # Block raised-module THT socket rows on both sides
        for rref in raised_refs:
            rfp = fps.get(rref)
            if rfp is None:
                continue
            tht_pts = [(pcbnew.ToMM(p.GetPosition().x), -pcbnew.ToMM(p.GetPosition().y))
                       for p in rfp.Pads() if p.GetDrillSizeX() > 0]
            ys = sorted({round(p[1], 2) for p in tht_pts})
            for y_row in ys:
                row_xs = [p[0] for p in tht_pts if abs(p[1] - y_row) < 0.2]
                if row_xs:
                    sb = (min(row_xs) - 1.5, y_row - 1.9, max(row_xs) + 1.5, y_row + 1.9)
                    fixed_mm["front"].append(sb)
                    fixed_mm["back"].append(sb)

    by_net = fp_pad_map()
    non_passive_refs = {r for r, fp in fps.items() if not is_symmetric_two_pin_passive(fp)}
    flipped = 0
    aligned = 0

    for _ in range(4):
        pass_flipped = 0
        pass_aligned = 0
        for ref in sorted(fps, key=_ref_sort_key):
            if only_refs is not None and ref not in only_refs:
                continue
            fp = fps[ref]
            if not is_symmetric_two_pin_passive(fp):
                continue
            pad_objs = {p.GetNumber(): p for p in fp.Pads() if p.GetNumber() in ("1", "2")}
            if len(pad_objs) != 2:
                continue
            n1, n2 = pad_objs["1"].GetNetname(), pad_objs["2"].GetNetname()
            if not n1 or not n2 or n1 == n2:
                continue

            def cur_p12():
                p1_v = pad_objs["1"].GetPosition()
                p2_v = pad_objs["2"].GetPosition()
                return (pcbnew.ToMM(p1_v.x), -pcbnew.ToMM(p1_v.y)), (pcbnew.ToMM(p2_v.x), -pcbnew.ToMM(p2_v.y))

            p1, p2 = cur_p12()
            cx, cy = (p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5

            # Prefer a shared non-passive parent carrying BOTH nets
            shared_cands = []
            for pref in sorted(non_passive_refs, key=_ref_sort_key):
                if pref == ref:
                    continue
                bn = by_net[pref]
                if n1 not in bn or n2 not in bn:
                    continue
                t1 = min(bn[n1], key=lambda q: math.hypot(q[0] - cx, q[1] - cy))
                t2 = min(bn[n2], key=lambda q: math.hypot(q[0] - cx, q[1] - cy))
                d_sum = math.hypot(t1[0] - cx, t1[1] - cy) + math.hypot(t2[0] - cx, t2[1] - cy)
                shared_cands.append((d_sum, pref, t1, t2))

            shared_parent = None
            if shared_cands:
                _, shared_parent, t1, t2 = min(shared_cands, key=lambda item: item[0])
            else:
                c1 = [q for o, bn in by_net.items() if o != ref and n1 in bn for q in bn[n1]]
                c2 = [q for o, bn in by_net.items() if o != ref and n2 in bn for q in bn[n2]]
                if not c1 or not c2:
                    continue
                t1 = min(c1, key=lambda q: math.hypot(q[0] - cx, q[1] - cy))
                t2 = min(c2, key=lambda q: math.hypot(q[0] - cx, q[1] - cy))

            def score(qa: tuple[float, float], qb: tuple[float, float]) -> float:
                d = math.hypot(qa[0] - t1[0], qa[1] - t1[1]) + math.hypot(qb[0] - t2[0], qb[1] - t2[1])
                return d + (CROSSING_PENALTY_MM if _segs_properly_cross(qa, t1, qb, t2) else 0.0)

            # 1. Zero-courtyard 180-deg uncrossing
            org = (pcbnew.ToMM(fp.GetPosition().x), -pcbnew.ToMM(fp.GetPosition().y))
            p1_f, p2_f = _rotate_pt_180(p1, org), _rotate_pt_180(p2, org)
            if score(p1_f, p2_f) < score(p1, p2) - 1e-4:
                new_rot = (round(fp.GetOrientation().AsDegrees()) + 180) % 360
                fp.SetOrientationDegrees(new_rot)
                p1, p2 = cur_p12()
                by_net[ref] = {n1: [p1], n2: [p2]}
                flipped += 1
                pass_flipped += 1

            # 2. Adjacent pin-pair midpoint alignment on shared parent (<= 4.0 mm pin pitch)
            if shared_parent is not None:
                pair_dist = math.hypot(t2[0] - t1[0], t2[1] - t1[1])
                mid_x, mid_y = (t1[0] + t2[0]) * 0.5, (t1[1] + t2[1]) * 0.5
                cur_org = (pcbnew.ToMM(fp.GetPosition().x), -pcbnew.ToMM(fp.GetPosition().y))
                if pair_dist <= 4.0 and math.hypot(cur_org[0] - mid_x, cur_org[1] - mid_y) <= 6.5:
                    pdx, pdy = p2[0] - p1[0], p2[1] - p1[1]
                    tdx, tdy = t2[0] - t1[0], t2[1] - t1[1]
                    pl, tl = math.hypot(pdx, pdy), math.hypot(tdx, tdy)
                    if pl > 1e-4 and tl > 1e-4 and abs((pdx * tdx + pdy * tdy) / (pl * tl)) > 0.9:
                        if abs(tdx) >= abs(tdy):
                            nx, ny = round(mid_x / GRID_MM) * GRID_MM, cur_org[1]
                        else:
                            nx, ny = cur_org[0], round(mid_y / GRID_MM) * GRID_MM
                        shift = math.hypot(nx - cur_org[0], ny - cur_org[1])
                        if 0.05 <= shift <= 3.0:
                            dx_s, dy_s = nx - cur_org[0], ny - cur_org[1]
                            old_box = _body_and_pad_mm(fp)
                            new_box = (old_box[0] + dx_s - 0.15, old_box[1] + dy_s - 0.15,
                                       old_box[2] + dx_s + 0.15, old_box[3] + dy_s + 0.15)
                            side = "back" if fp.IsFlipped() else "front"
                            clash = False
                            if side in bounds_mm:
                                bx0, by0, bx1, by1 = bounds_mm[side]
                                if new_box[0] < bx0 or new_box[1] < by0 or new_box[2] > bx1 or new_box[3] > by1:
                                    clash = True
                            if not clash:
                                for obs_b in fixed_mm[side]:
                                    if _boxes_clash(new_box, obs_b):
                                        clash = True
                                        break
                            if not clash:
                                for oref, ofp in fps.items():
                                    if oref == ref or oref in raised_refs:
                                        continue
                                    oside = "back" if ofp.IsFlipped() else "front"
                                    if oside != side:
                                        continue
                                    if _boxes_clash(new_box, _body_and_pad_mm(ofp)):
                                        clash = True
                                        break
                            if not clash:
                                np1 = (p1[0] + dx_s, p1[1] + dy_s)
                                np2 = (p2[0] + dx_s, p2[1] + dy_s)
                                if score(np1, np2) <= score(p1, p2) + 1e-4:
                                    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(nx), pcbnew.FromMM(-ny)))
                                    p1, p2 = cur_p12()
                                    by_net[ref] = {n1: [p1], n2: [p2]}
                                    aligned += 1
                                    pass_aligned += 1
                                    p1_f2, p2_f2 = _rotate_pt_180(p1, (nx, ny)), _rotate_pt_180(p2, (nx, ny))
                                    if score(p1_f2, p2_f2) < score(p1, p2) - 1e-4:
                                        fp.SetOrientationDegrees((round(fp.GetOrientation().AsDegrees()) + 180) % 360)
                                        p1, p2 = cur_p12()
                                        by_net[ref] = {n1: [p1], n2: [p2]}
                                        flipped += 1
                                        pass_flipped += 1
        if pass_flipped == 0 and pass_aligned == 0:
            break

    return {"flipped": flipped, "aligned": aligned}


def solve_board(
    board: pcbnew.BOARD,
    plan: dict,
    board_name: str,
    parts_json_path: Path,
    only_refs: set[str] | None = None,
) -> dict[str, tuple[float, float, int, str]]:
    """Run deterministic 2-stage CP-SAT placement on `board` and apply solved positions."""
    meta_by_ref = {p["ref"]: p for p in json.loads(parts_json_path.read_text())}
    planned = plan.get("parts", {})
    placement_cfg = plan.get("placement", {})
    default_side = placement_cfg.get("default_side", "front")
    heights = plan.get("heights", {})
    default_h = heights.get("default", 1.2)

    frame = plan["frame"]
    w_mm, h_mm = frame["size"]["x"], frame["size"]["y"]
    spacious = min(w_mm, h_mm) >= 17.0

    all_parts: dict[str, PartSpec] = {}
    anchors: dict[str, PartSpec] = {}
    placed_coords: dict[str, tuple[int, int, int]] = {}

    for fp in sorted(board.Footprints(), key=lambda f: _ref_sort_key(f.GetReference())):
        ref = fp.GetReference()
        p_cfg = planned.get(ref, {})
        is_locked = bool(p_cfg.get("locked", False)) or (only_refs is not None and ref not in only_refs)
        if ref in planned and "x" in p_cfg and "y" in p_cfg and is_locked:
            side = p_cfg.get("side", "front")
            rot = int(p_cfg.get("rot", 0)) % 360
            _set_side(fp, side == "back")
            fp.SetOrientationDegrees(rot)
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(p_cfg["x"]), pcbnew.FromMM(-p_cfg["y"])))
            fp.SetLocked(bool(p_cfg.get("locked", False)))
        elif is_locked:
            side = "back" if fp.IsFlipped() else "front"
            rot = round(fp.GetOrientation().AsDegrees()) % 360
        else:
            side = p_cfg.get("side", default_side)
            rot = 0

        rots = (rot,) if is_locked else (0, 90, 180, 270)
        blk = p_cfg.get("block") or meta_by_ref.get(ref, {}).get("place", "misc")
        spec = _measure_part(fp, side, blk, heights.get(ref, default_h), is_locked, rots, spacious)
        all_parts[ref] = spec
        if is_locked:
            anchors[ref] = spec
            placed_coords[ref] = (
                g_round(pcbnew.ToMM(fp.GetPosition().x)),
                g_round(-pcbnew.ToMM(fp.GetPosition().y)),
                rot,
            )

    board_w_grid = g_round(w_mm)
    board_h_grid = g_round(h_mm)
    base_margin = g_ceil(max(frame["edge_clearance"], 0.35))
    margins = placement_cfg.get("edge_margins", {})
    edge_margin_grid: dict[str, tuple[int, int, int, int]] = {}
    for side in ("front", "back"):
        sm = margins.get(side, {})
        edge_margin_grid[side] = (
            g_ceil(sm.get("x0", base_margin * GRID_MM)),
            g_ceil(sm.get("y0", base_margin * GRID_MM)),
            g_ceil(sm.get("x1", base_margin * GRID_MM)),
            g_ceil(sm.get("y1", base_margin * GRID_MM)),
        )

    fixed_obs, height_caps = _anchor_obstacles(board, plan, anchors)

    # Stage 1: all non-locked active ICs, inductors, discrete semiconductors and fuses
    stage1_refs = [
        ref for ref, s in sorted(all_parts.items(), key=lambda kv: _ref_sort_key(kv[0]))
        if not s.locked and not s.is_passive
    ]
    if stage1_refs:
        s1 = _solve_subset(
            all_parts, stage1_refs, placed_coords, fixed_obs, height_caps,
            board_w_grid, board_h_grid, edge_margin_grid, STAGE1_SECONDS, f"{board_name}:stage1",
        )
        placed_coords.update(s1)

    # Stage 2: 2-pin passives solved in logical functional batches
    passive_refs = [
        ref for ref, s in sorted(all_parts.items(), key=lambda kv: _ref_sort_key(kv[0]))
        if not s.locked and s.is_passive
    ]
    by_block: dict[str, list[str]] = {}
    for ref in passive_refs:
        by_block.setdefault(all_parts[ref].block, []).append(ref)

    def block_priority(item: tuple[str, list[str]]) -> tuple[int, str]:
        blk, refs = item
        # Solve tight switching / charge-pump / analog blocks before generic I/O blocks
        has_hp = any(
            any(pk.split(":", 1)[1].startswith(HIGH_PRIORITY_PREFIXES)
                for pk in next(iter(all_parts[r].orients.values())).pads)
            for r in refs
        )
        return (0 if has_hp else 1, blk)

    # Within `buck5v`, solve the critical HF switching/bootstrap/divider passives (C1, C4, R1..R4)
    # in an inner sub-batch BEFORE bulk input/output caps (C2, C3, C5..C7) so C1 & C4 claim the
    # immediate <4.5 mm perimeter of U1.
    batches: list[tuple[str, list[str]]] = []
    for blk, batch_refs in sorted(by_block.items(), key=block_priority):
        if blk == "buck5v" and len(batch_refs) > 6:
            inner = [
                r for r in batch_refs
                if r.startswith("R") or _cap_farads_approx(all_parts[r].value) <= 150e-9
            ]
            outer = [r for r in batch_refs if r not in inner]
            if inner:
                batches.append((f"{blk}_hf", inner))
            if outer:
                batches.append((f"{blk}_bulk", outer))
        else:
            batches.append((blk, batch_refs))

    for blk, batch_refs in batches:
        s2 = _solve_subset(
            all_parts, batch_refs, placed_coords, fixed_obs, height_caps,
            board_w_grid, board_h_grid, edge_margin_grid, STAGE2_SECONDS, f"{board_name}:stage2:{blk}",
        )
        placed_coords.update(s2)

    for ref, spec in sorted(all_parts.items(), key=lambda kv: _ref_sort_key(kv[0])):
        if spec.locked:
            continue
        gx, gy, rot = placed_coords[ref]
        x_mm = round(gx * GRID_MM, 3)
        y_mm = round(gy * GRID_MM, 3)
        _set_side(spec.fp, spec.side == "back")
        spec.fp.SetOrientationDegrees(rot)
        spec.fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(-y_mm)))
        spec.fp.SetLocked(False)

    # Post-placement zero-courtyard 180-deg uncrossing & shared-parent pin-pair alignment
    ua = uncross_and_align_passives(board, plan, only_refs=only_refs)

    result: dict[str, tuple[float, float, int, str]] = {}
    for ref, spec in sorted(all_parts.items(), key=lambda kv: _ref_sort_key(kv[0])):
        if spec.locked:
            continue
        p = spec.fp.GetPosition()
        result[ref] = (
            round(pcbnew.ToMM(p.x), 3),
            round(-pcbnew.ToMM(p.y), 3),
            round(spec.fp.GetOrientation().AsDegrees()) % 360,
            spec.side,
        )

    print(
        f"{board_name}: CP-SAT placed {len(stage1_refs)} Stage-1 active/semi parts + "
        f"{len(passive_refs)} Stage-2 passives across {len(by_block)} batches "
        f"({len(anchors)} fixed anchors; uncrossed {ua['flipped']}, aligned {ua['aligned']})"
    )
    return result
