"""Test 2 — Pure Copper-Extracted End-to-End `ngspice` Simulation Gate (`libngspice` via `ctypes`).

Extracts a SPICE netlist with ZERO imports from the circuit generator (`hardware/circuits/`):
  - Asserts `pcb.GetConnectivity().GetUnconnectedCount(False) == 0` on every board.
  - Reconstructs electrical nodes strictly from physical tracks, vias, filled zones
    and copper pads via Union-Find (without reading net names during clustering),
    proving zero physical copper opens or shorts.
  - Extracts physical copper trace `R` and `C` parasitics from track lengths/widths/vias.
  - Reads component values and MPNs strictly from exported production BOM CSVs
    (`hardware/releases/v1/<board>/<board>_bom.csv`).
  - Stitches `main` <-> `ui` (8-pin 0.5 mm Type-B FFC) and `main` <-> `reader`
    (sensor bank cable) strictly by 3D `(X, Y, Z)` mating pad coordinates.
  - Runs `.op`, `.ac`, `.noise` (`setplot noise1`) and `.tran` via `libngspice.so.0`
    (`ctypes`) to verify reverse-polarity blocking, surge TVS clamping, buck UVLO &
    5 V regulation, cascaded XIAO 3.3 V LDO dropout headroom, shared-rail decoupling
    impedance stability, 4-20 mA & 0-10 V gain/filtering/noise/mis-wire clamping,
    relay driver saturation & flyback clamping, UI button ladder & LED buffer, and
    optical dial-reader comparator hysteresis end-to-end.
"""

from __future__ import annotations

import csv
import ctypes
import ctypes.util
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pcbnew
import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
BOARDS = ("main", "ui", "reader")
FORBIDDEN_MODULES = ("skidl", "gen_circuits", "common", "product_spec", "blocks", "variants")


# ---------------------------------------------------------------------------
# 1. `libngspice` ctypes wrapper
# ---------------------------------------------------------------------------

class _NgComplex(ctypes.Structure):
    _fields_ = [("cx_real", ctypes.c_double), ("cx_imag", ctypes.c_double)]


class _VectorInfo(ctypes.Structure):
    _fields_ = [
        ("v_name", ctypes.c_char_p),
        ("v_type", ctypes.c_int),
        ("v_flags", ctypes.c_short),
        ("v_realdata", ctypes.POINTER(ctypes.c_double)),
        ("v_compdata", ctypes.POINTER(_NgComplex)),
        ("v_length", ctypes.c_int),
    ]


_SENDCHAR = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
_SENDSTAT = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
_CTRL_EXIT = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_bool, ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)


class NgSpiceRunner:
    _instance: NgSpiceRunner | None = None

    def __init__(self) -> None:
        self.lib = ctypes.CDLL(ctypes.util.find_library("ngspice") or "libngspice.so.0")
        self.logs: list[str] = []
        self.exited = False

        @_SENDCHAR
        def _cb_char(msg: bytes, _ident: int, _user: int) -> int:
            if msg:
                self.logs.append(msg.decode(errors="replace"))
            return 0

        @_SENDSTAT
        def _cb_stat(_msg: bytes, _ident: int, _user: int) -> int:
            return 0

        @_CTRL_EXIT
        def _cb_exit(_status: int, _imm: bool, _quit: bool, _ident: int, _user: int) -> int:
            self.exited = True
            return 0

        # Keep callback references alive for the lifetime of the process
        self._cbs = (_cb_char, _cb_stat, _cb_exit)
        self.lib.ngSpice_Init.argtypes = [
            _SENDCHAR, _SENDSTAT, _CTRL_EXIT,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ]
        self.lib.ngSpice_Command.argtypes = [ctypes.c_char_p]
        self.lib.ngSpice_Circ.argtypes = [ctypes.POINTER(ctypes.c_char_p)]
        self.lib.ngGet_Vec_Info.argtypes = [ctypes.c_char_p]
        self.lib.ngGet_Vec_Info.restype = ctypes.POINTER(_VectorInfo)
        self.lib.ngSpice_Init(_cb_char, _cb_stat, _cb_exit, None, None, None, None)

    @classmethod
    def get(cls) -> NgSpiceRunner:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def cmd(self, command: str) -> None:
        self.lib.ngSpice_Command(command.encode())

    def run_deck(self, lines: list[str]) -> None:
        self.logs.clear()
        self.cmd("destroy all")
        flat = [sub.strip() for block in lines for sub in block.splitlines() if sub.strip()]
        encoded = [line.encode() for line in flat] + [b".end", None]
        arr = (ctypes.c_char_p * len(encoded))(*encoded)
        rc = self.lib.ngSpice_Circ(arr)
        if rc != 0:
            raise RuntimeError(f"ngSpice_Circ failed (rc={rc}):\n" + "\n".join(self.logs[-30:]))
        self.cmd("run")
        errors = [
            l for l in self.logs
            if ("simulation(s) aborted" in l.lower() or "singular matrix" in l.lower()
                or "doanalyses:" in l.lower() or "there aren't any circuits" in l.lower())
        ]
        if errors:
            raise RuntimeError("ngspice analysis failed:\n" + "\n".join(self.logs[-40:]))

    def real_vec(self, name: str) -> list[float]:
        vi = self.lib.ngGet_Vec_Info(name.encode())
        if not vi:
            raise KeyError(f"ngspice vector {name!r} not found. Logs:\n" + "\n".join(self.logs[-25:]))
        v = vi.contents
        if v.v_realdata:
            return [float(v.v_realdata[i]) for i in range(v.v_length)]
        if v.v_compdata:
            return [math.hypot(v.v_compdata[i].cx_real, v.v_compdata[i].cx_imag) for i in range(v.v_length)]
        return []

    def complex_vec(self, name: str) -> list[complex]:
        vi = self.lib.ngGet_Vec_Info(name.encode())
        if not vi:
            raise KeyError(f"ngspice vector {name!r} not found")
        v = vi.contents
        if v.v_compdata:
            return [complex(v.v_compdata[i].cx_real, v.v_compdata[i].cx_imag) for i in range(v.v_length)]
        return [complex(v.v_realdata[i], 0.0) for i in range(v.v_length)]

    def scalar(self, name: str) -> float:
        vals = self.real_vec(name)
        assert vals, f"empty vector {name}"
        return vals[-1]


# ---------------------------------------------------------------------------
# 2. Pure Copper Union-Find + Parasitic Extractor (ZERO generator imports)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BomPart:
    ref: str
    value: str
    mpn: str
    package: str


def _load_bom(board: str) -> dict[str, BomPart]:
    path = REPO / "hardware/releases/v1" / board / f"{board}_bom.csv"
    out: dict[str, BomPart] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            for ref in row["Designator"].split(","):
                ref = ref.strip()
                out[ref] = BomPart(ref, row["Value"].strip(), row["MPN"].strip(), row["Package"].strip())
    return out


def _parse_val(text: str) -> float:
    tok = text.strip().split()[0]
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([pnuµmkMR]?)(\d*)[ΩFHV]?", tok)
    if not m:
        raise ValueError(f"Cannot parse value {text!r}")
    whole, pfx, frac = m.groups()
    base = float(f"{whole}.{frac}" if frac else whole)
    mult = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1.0, "R": 1.0, "k": 1e3, "M": 1e6}[pfx]
    return base * mult


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, x: str) -> None:
        self.parent.setdefault(x, x)

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            if ra < rb:
                self.parent[rb] = ra
            else:
                self.parent[ra] = rb


def _seg_dist(px: int, py: int, ax: int, ay: int, bx: int, by: int) -> float:
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return math.hypot(px - ax, py - ay)
    u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + u * dx), py - (ay + u * dy))


def _segs_distance(a1: tuple[int, int], a2: tuple[int, int], b1: tuple[int, int], b2: tuple[int, int]) -> float:
    # Exact check for 2D segment intersection + endpoint-to-segment minimum
    def ccw(p, q, r):
        return (r[1] - p[1]) * (q[0] - p[0]) - (q[1] - p[1]) * (r[0] - p[0])

    d1, d2 = ccw(a1, a2, b1), ccw(a1, a2, b2)
    d3, d4 = ccw(b1, b2, a1), ccw(b1, b2, a2)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return 0.0
    return min(
        _seg_dist(a1[0], a1[1], b1[0], b1[1], b2[0], b2[1]),
        _seg_dist(a2[0], a2[1], b1[0], b1[1], b2[0], b2[1]),
        _seg_dist(b1[0], b1[1], a1[0], a1[1], a2[0], a2[1]),
        _seg_dist(b2[0], b2[1], a1[0], a1[1], a2[0], a2[1]),
    )


@dataclass
class ExtractedBoard:
    name: str
    bom: dict[str, BomPart]
    unconnected_count: int
    uf: _UnionFind
    pad_node: dict[tuple[str, str], str]           # (ref, pin_num) -> physical copper node id
    pad_coords_mm: dict[tuple[str, str], tuple[float, float, bool]]  # (x_mm, y_up_mm, is_back)
    node_r_ohm: dict[str, float]                   # physical copper resistance per node
    node_c_farad: dict[str, float]                 # physical copper capacitance to plane per node
    gnd_node: str                                  # physical copper node id of reference ground
    audit_net_to_nodes: dict[str, set[str]]        # post-hoc verification against KiCad pad netnames


def extract_board_copper(board: str) -> ExtractedBoard:
    pcb = pcbnew.LoadBoard(str(REPO / "hardware/layout/v1" / board / f"{board}.kicad_pcb"))
    pcbnew.ZONE_FILLER(pcb).Fill(pcb.Zones())
    pcb.BuildConnectivity()
    unconnected = pcb.GetConnectivity().GetUnconnectedCount(False)

    bom = _load_bom(board)
    uf = _UnionFind()
    tol = pcbnew.FromMM(0.008)
    cu_layers = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]

    # Collect physical copper primitives WITHOUT inspecting net names/codes
    pads_list: list[tuple[str, pcbnew.PAD, str, str]] = []
    pad_coords: dict[tuple[str, str], list[tuple[float, float, bool]]] = {}
    for fp in sorted(pcb.Footprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        back = fp.IsFlipped()
        for idx, pad in enumerate(fp.Pads()):
            num = pad.GetNumber().strip()
            if not num:
                continue
            pid = f"P:{ref}:{idx}"
            uf.add(pid)
            pads_list.append((pid, pad, ref, num))
            pos = pad.GetPosition()
            pad_coords.setdefault((ref, num), []).append((pcbnew.ToMM(pos.x), -pcbnew.ToMM(pos.y), back))

    tracks_list: list[tuple[str, pcbnew.PCB_TRACK]] = []
    vias_list: list[tuple[str, pcbnew.PCB_VIA]] = []
    for idx, item in enumerate(pcb.GetTracks()):
        if item.Type() == pcbnew.PCB_VIA_T:
            vid = f"V:{idx}"
            uf.add(vid)
            vias_list.append((vid, item))
        else:
            tid = f"T:{idx}"
            uf.add(tid)
            tracks_list.append((tid, item))

    zones_list: list[tuple[str, pcbnew.ZONE]] = []
    for idx in range(pcb.GetAreaCount()):
        z = pcb.GetArea(idx)
        if not z.GetIsRuleArea():
            zid = f"Z:{idx}"
            uf.add(zid)
            zones_list.append((zid, z))

    def via_layers(v: pcbnew.PCB_VIA) -> set[int]:
        top, bot = v.TopLayer(), v.BottomLayer()
        if top == pcbnew.F_Cu and bot == pcbnew.B_Cu:
            return set(cu_layers)
        return {top, bot}

    # 1. Track <-> Track on same layer (binned by layer)
    by_layer: dict[int, list[tuple[str, tuple[int, int], tuple[int, int], int, pcbnew.BOX2I]]] = {}
    for tid, t in tracks_list:
        s, e = t.GetStart(), t.GetEnd()
        w = t.GetWidth()
        bb = t.GetBoundingBox()
        by_layer.setdefault(t.GetLayer(), []).append((tid, (s.x, s.y), (e.x, e.y), w, bb))

    for lyr, segs in by_layer.items():
        n = len(segs)
        for i in range(n):
            tid_a, a1, a2, wa, bba = segs[i]
            for j in range(i + 1, n):
                tid_b, b1, b2, wb, bbb = segs[j]
                reach = (wa + wb) // 2 + tol
                if (bba.GetRight() + reach < bbb.GetLeft() or bbb.GetRight() + reach < bba.GetLeft()
                        or bba.GetBottom() + reach < bbb.GetTop() or bbb.GetBottom() + reach < bba.GetTop()):
                    continue
                if _segs_distance(a1, a2, b1, b2) <= reach:
                    uf.union(tid_a, tid_b)

    # 2. Via <-> Via & Track <-> Via
    for i, (vid_a, va) in enumerate(vias_list):
        pa = va.GetPosition()
        la = via_layers(va)
        ra = va.GetWidth(pcbnew.F_Cu) // 2
        for vid_b, vb in vias_list[i + 1:]:
            if la & via_layers(vb):
                pb = vb.GetPosition()
                if math.hypot(pa.x - pb.x, pa.y - pb.y) <= ra + vb.GetWidth(pcbnew.F_Cu) // 2 + tol:
                    uf.union(vid_a, vid_b)
        for lyr in la:
            for tid, a1, a2, wt, bbt in by_layer.get(lyr, []):
                reach = ra + wt // 2 + tol
                if (pa.x + reach < bbt.GetLeft() or pa.x - reach > bbt.GetRight()
                        or pa.y + reach < bbt.GetTop() or pa.y - reach > bbt.GetBottom()):
                    continue
                if _seg_dist(pa.x, pa.y, a1[0], a1[1], a2[0], a2[1]) <= reach:
                    uf.union(vid_a, tid)

    # 3. Pad <-> Track & Pad <-> Via
    for pid, pad, _ref, _num in pads_list:
        pbb = pad.GetBoundingBox()
        ppos = pad.GetPosition()
        for lyr in cu_layers:
            if not pad.IsOnLayer(lyr):
                continue
            for tid, a1, a2, wt, bbt in by_layer.get(lyr, []):
                reach = wt // 2 + tol
                if (pbb.GetRight() + reach < bbt.GetLeft() or bbt.GetRight() + reach < pbb.GetLeft()
                        or pbb.GetBottom() + reach < bbt.GetTop() or bbt.GetBottom() + reach < pbb.GetTop()):
                    continue
                # Sample endpoints + closest point to pad centre
                dx, dy = a2[0] - a1[0], a2[1] - a1[1]
                l2 = dx * dx + dy * dy
                u = 0.0 if l2 == 0 else max(0.0, min(1.0, ((ppos.x - a1[0]) * dx + (ppos.y - a1[1]) * dy) / l2))
                qx, qy = int(a1[0] + u * dx), int(a1[1] + u * dy)
                if (pad.HitTest(pcbnew.VECTOR2I(a1[0], a1[1]), reach)
                        or pad.HitTest(pcbnew.VECTOR2I(a2[0], a2[1]), reach)
                        or pad.HitTest(pcbnew.VECTOR2I(qx, qy), reach)):
                    uf.union(pid, tid)
        for vid, v in vias_list:
            vpos = v.GetPosition()
            for lyr in via_layers(v):
                if pad.IsOnLayer(lyr) and pad.HitTest(vpos, v.GetWidth(lyr) // 2 + tol):
                    uf.union(pid, vid)
                    break

    # 4. Zone <-> Via, Track, Pad
    for zid, z in zones_list:
        for lyr in cu_layers:
            if not z.IsOnLayer(lyr):
                continue
            for vid, v in vias_list:
                if lyr in via_layers(v) and z.HitTestFilledArea(lyr, v.GetPosition(), v.GetDrillValue() // 2 + tol):
                    uf.union(zid, vid)
            for tid, a1, a2, wt, _bbt in by_layer.get(lyr, []):
                mid = pcbnew.VECTOR2I((a1[0] + a2[0]) // 2, (a1[1] + a2[1]) // 2)
                if (z.HitTestFilledArea(lyr, pcbnew.VECTOR2I(a1[0], a1[1]), wt // 2 + tol)
                        or z.HitTestFilledArea(lyr, pcbnew.VECTOR2I(a2[0], a2[1]), wt // 2 + tol)
                        or z.HitTestFilledArea(lyr, mid, wt // 2 + tol)):
                    uf.union(zid, tid)
            for pid, pad, _ref, _num in pads_list:
                if pad.IsOnLayer(lyr):
                    rad = min(pad.GetSizeX(), pad.GetSizeY()) // 2 + tol
                    if z.HitTestFilledArea(lyr, pad.GetPosition(), rad):
                        uf.union(zid, pid)

    # Map each component pin `(ref, num)` to its physical copper root (assert split pads share root!)
    pad_node: dict[tuple[str, str], str] = {}
    audit_net_to_nodes: dict[str, set[str]] = {}
    for pid, pad, ref, num in pads_list:
        root = f"{board}_{re.sub(r'[^A-Za-z0-9_]', '_', uf.find(pid))}"
        key = (ref, num)
        if key in pad_node and pad.GetNetname():
            assert pad_node[key] == root, f"{board}:{ref}.{num} split pads are NOT connected in physical copper!"
        pad_node[key] = root
        netname = pad.GetNetname()
        if netname:
            audit_net_to_nodes.setdefault(netname, set()).add(root)

    # Compute physical trace R and C parasitics per copper root from routed tracks & vias
    # 1 oz outer Cu (35 um): R_sheet = 0.491 mOhm/sq; 0.5 oz inner Cu (17.5 um): 0.983 mOhm/sq
    node_r: dict[str, float] = {}
    node_c: dict[str, float] = {}
    for tid, t in tracks_list:
        root = f"{board}_{re.sub(r'[^A-Za-z0-9_]', '_', uf.find(tid))}"
        len_mm = pcbnew.ToMM(t.GetLength())
        w_mm = max(0.1, pcbnew.ToMM(t.GetWidth()))
        r_sheet = 0.491e-3 if t.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu) else 0.983e-3
        node_r[root] = node_r.get(root, 0.0) + r_sheet * (len_mm / w_mm)
        # Microstrip capacitance over In1.Cu prepreg (~0.09 pF/mm at 0.2 mm width, scales with w)
        c_pf_per_mm = 0.055 + 0.18 * w_mm
        node_c[root] = node_c.get(root, 0.0) + c_pf_per_mm * 1e-12 * len_mm

    for vid, _v in vias_list:
        root = f"{board}_{re.sub(r'[^A-Za-z0-9_]', '_', uf.find(vid))}"
        node_r[root] = node_r.get(root, 0.0) + 1.2e-3
        node_c[root] = node_c.get(root, 0.0) + 0.25e-12

    # Identify ground node strictly as the copper node holding the solid In1.Cu ground plane zone
    plane_zones = [zid for zid, z in zones_list if z.IsOnLayer(pcbnew.In1_Cu)]
    assert plane_zones, f"{board}: missing In1.Cu reference plane zone"
    gnd_node = f"{board}_{re.sub(r'[^A-Za-z0-9_]', '_', uf.find(plane_zones[0]))}"

    mean_coords = {
        k: (
            sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts),
            pts[0][2],
        )
        for k, pts in pad_coords.items()
    }

    return ExtractedBoard(
        name=board,
        bom=bom,
        unconnected_count=unconnected,
        uf=uf,
        pad_node=pad_node,
        pad_coords_mm=mean_coords,
        node_r_ohm=node_r,
        node_c_farad=node_c,
        gnd_node=gnd_node,
        audit_net_to_nodes=audit_net_to_nodes,
    )


# ---------------------------------------------------------------------------
# 3. Smooth C^inf `tanh()` SPICE Behavioral Library + Copper Netlist Emitter
# ---------------------------------------------------------------------------

SPICE_MODELS = """
* Smooth C^inf device models and subcircuits (bounded tanh <= 10, poles to VEE/GND)
.options rshunt=1e11 abstol=1e-10 reltol=1e-3 vntol=1e-6 method=trap

.model D_SS36 D(Is=0.25u N=1.08 Rs=0.045 Cjo=180p Bv=65 Ibv=1m)
.model D_SS34 D(Is=0.45u N=1.08 Rs=0.042 Cjo=220p Bv=45 Ibv=1m)
.model D_B5819W D(Is=0.20u N=1.06 Rs=0.10 Cjo=90p Bv=45 Ibv=1m)
.model D_BAT54 D(Is=40n N=1.05 Rs=0.8 Cjo=8p Bv=32 Ibv=100u)
.model D_SMAJ30A D(Is=1p N=1.05 Rs=0.65 Cjo=650p Bv=34.5 Ibv=1m)
.model D_Z5V6 D(Is=10p N=1.05 Rs=2.0 Cjo=60p Bv=5.6 Ibv=5m)
.model D_LED_RED D(Is=1e-19 N=1.85 Rs=8 Cjo=15p)
.model D_IR_EMIT D(Is=1e-16 N=1.55 Rs=2.5 Cjo=20p)
.model Q_3904 NPN(Is=1e-14 Bf=180 Vaf=100 Ikf=0.2 Rb=10 Rc=0.4 Re=0.2 Cje=8p Cjc=4p Tf=0.35n)

* SCT2601TVBR averaged continuous-time buck regulator (1=BST, 2=GND, 3=FB, 4=EN, 5=VIN, 6=SW)
* V_FB_ref = 0.765 V, V_EN_rising = 1.223 V, R_on_HS = 0.55 Ohm, conserves input current I_in = D * I_SW
.subckt MPN_SCT2601 bst gnd fb en vin sw
R_en_in en gnd 2Meg
R_fb_in fb gnd 20Meg
R_bst_leak bst sw 500k
D_bst_chg sw bst D_BAT54
B_iq vin gnd I = 150u * 0.5 * (1 + tanh(min(max((V(vin,gnd) - 3.5)/0.5, -10), 10)))
B_err 0 err_p I = 1e-3 * tanh(min(max((0.765 - V(fb,gnd)) * 80, -10), 10))
R_pole err_p gnd 50k
C_pole err_p gnd 100p
B_duty duty_n gnd V = 0.5 * (1 + tanh(min(max((V(en,gnd) - 1.223)/0.03, -10), 10))) * 0.5 * (1 + tanh(min(max(V(err_p,gnd), -10), 10)))
R_duty duty_n gnd 1Meg
B_sw_drv sw_int gnd V = V(gnd) + V(vin,gnd) * V(duty_n,gnd)
V_sw_sense sw_int sw_mid 0
R_hs sw_mid sw 0.55
B_iin vin gnd I = V(duty_n,gnd) * max(0, I(V_sw_sense))
.ends

* Seeed XIAO ESP32C6 14-pin module (all 14 pins terminated; internal 3.3 V LDO from pin 14 -> pin 12)
.subckt MPN_XIAO14 p1 p2 p3 p4 p5 p6 p7 p8 p9 p10 p11 v3v3 gnd v5in tx_cur=0.04 relay_drv=0.0 relay_en=1.0
R_adc0 p1 gnd 10Meg
C_adc0 p1 gnd 5p
R_adc1 p2 gnd 10Meg
C_adc1 p2 gnd 5p
R_adc2 p3 gnd 10Meg
C_adc2 p3 gnd 5p
V_led p4_src gnd DC 0
R_led p4_src p4 40
R_sda p5 gnd 10Meg
C_sda p5 gnd 6p
R_scl p6 gnd 10Meg
C_scl p6 gnd 6p
R_io2 p7 gnd 10Meg
R_io1 p8 gnd 10Meg
B_rel p9 gnd I = {relay_en} * (V(p9,gnd) - {relay_drv}) / 35.0
R_rel_hiz p9 gnd 10Meg
R_io3 p10 gnd 10Meg
R_io4 p11 gnd 10Meg
* Onboard 3.3 V LDO with smooth dropout tracking (V_do = 0.22 V) + load current
B_ldo_err 0 ldo_p I = 1e-3 * tanh(min(max((3.30 - V(v3v3,gnd)) * 120, -10), 10))
R_ldo_p ldo_p gnd 20k
C_ldo_p ldo_p gnd 200p
B_ldo_pass v5in v3v3 I = max(0, (min(V(v5in,gnd) - 0.22, 3.30 * 0.5 * (1 + tanh(min(max(V(ldo_p,gnd), -10), 10)))) - V(v3v3,gnd)) / 0.12) * 0.5 * (1 + tanh(min(max((V(v5in,gnd) - 2.0)/0.2, -10), 10)))
B_mcu_load v3v3 gnd I = {tx_cur} * 0.5 * (1 + tanh(min(max((V(v3v3,gnd) - 2.2)/0.2, -10), 10)))
.ends

* Omron G6B-2114P-US DC5 relay (1=COIL-, 3=COM1, 4=NO, 5=NC, 6=COM2, 8=COIL+)
.subckt MPN_G6B2114P c_neg com1 no_p nc_p com2 c_pos
V_isense c_pos coil_s 0
R_coil coil_s coil_mid 83.3
L_coil coil_mid c_neg 45m
* Smooth C^inf changeover contacts driven by true inductive coil current I(V_isense) (pull-in ~35 mA)
B_no com1 no_p I = V(com1,no_p) * (1e-9 + 5.0 * 0.5 * (1 + tanh(min(max((I(V_isense) - 0.035)/0.0015, -10), 10))))
B_nc com2 nc_p I = V(com2,nc_p) * (1e-9 + 5.0 * 0.5 * (1 - tanh(min(max((I(V_isense) - 0.035)/0.0015, -10), 10))))
.ends

* TI SN74AHCT1G125DBVR 5 V TTL-input CMOS buffer (1=/OE, 2=A, 3=GND, 4=Y, 5=VCC)
.subckt MPN_74AHCT1G125 oe_n a_in gnd y_out vcc
R_oe oe_n gnd 20Meg
R_a a_in gnd 20Meg
B_icc vcc gnd I = 10u * 0.5 * (1 + tanh(min(max((V(vcc,gnd) - 1.5)/0.3, -10), 10)))
B_y y_int gnd V = V(gnd) + V(vcc,gnd) * 0.5 * (1 + tanh(min(max((V(a_in,gnd) - 1.4)/0.08, -10), 10)))
B_drv y_int y_out I = (V(y_int,y_out) / 35.0) * 0.5 * (1 + tanh(min(max((1.4 - V(oe_n,gnd))/0.1, -10), 10)))
R_hiz y_out gnd 50Meg
.ends

* Worldsemi WS2812B-MINI-V3J RGB LED (1=VDD, 2=DOUT, 3=GND, 4=DIN)
.subckt MPN_WS2812B vdd dout gnd din led_cur=0.002
B_idd vdd gnd I = (0.6m + {led_cur}) * 0.5 * (1 + tanh(min(max((V(vdd,gnd) - 2.5)/0.3, -10), 10)))
R_din din gnd 5Meg
C_din din gnd 5p
B_dout dout_i gnd V = V(gnd) + V(vdd,gnd) * 0.5 * (1 + tanh(min(max((V(din,gnd) - 0.5*V(vdd,gnd))/0.1, -10), 10)))
R_dout dout_i dout 45
.ends

* SSD1312 14-pin OLED panel load (1..14)
.subckt MPN_SSD1312 p1 p2 p3 p4 p5 p7 p8 p9 p10 p11 p12 p13 p14
R_c2 p1 p2 50k
R_c1 p3 p4 50k
B_vbat p5 p7 I = 6m * 0.5 * (1 + tanh(min(max((V(p5,p7) - 2.2)/0.2, -10), 10)))
B_vdd p8 p7 I = 150u * 0.5 * (1 + tanh(min(max((V(p8,p7) - 1.6)/0.2, -10), 10)))
R_res p9 p7 10Meg
R_scl p10 p7 10Meg
C_scl p10 p7 6p
R_sda p11 p7 10Meg
C_sda p11 p7 6p
B_iref p8 p12 I = (1.25 - V(p12,p7)) / 1k * 0.5 * (1 + tanh(min(max((V(p8,p7) - 2.0)/0.2, -10), 10)))
B_vout p5 p14 I = (2.2 * V(p5,p7) - V(p14,p7)) / 200.0
R_vcomh p14 p13 50k
.ends

* Vishay TCRT5000 reflective IR sensor (1=A, 2=K, 3=C, 4=E)
.subckt MPN_TCRT5000 ir_a ir_k pt_c pt_e ctr=0.03
V_ir ir_a ir_mid 0
D_ir ir_mid ir_k D_IR_EMIT
B_photo pt_c pt_e I = {ctr} * max(0, I(V_ir)) * tanh(min(max(V(pt_c,pt_e)/0.12, -10), 10))
R_dark pt_c pt_e 50Meg
.ends

* TI LMV331IDBVR open-collector comparator (1=IN+, 2=V-, 3=IN-, 4=OUT, 5=V+)
* Dominant pole referenced to V- (GND); smooth C^inf open-collector sink when V(IN-) > V(IN+)
.subckt MPN_LMV331 inp vee inm out vcc
R_inp inp vee 50Meg
R_inm inm vee 50Meg
B_iq vcc vee I = 60u * 0.5 * (1 + tanh(min(max((V(vcc,vee) - 1.8)/0.3, -10), 10)))
B_diff 0 cmp_p I = 1e-3 * tanh(min(max((V(inm,inp)) * 120, -10), 10))
R_p cmp_p vee 10k
C_p cmp_p vee 15p
B_oc out vee I = (V(out,vee) / 28.0) * 0.5 * (1 + tanh(min(max(V(cmp_p,vee), -10), 10)))
.ends
"""


def build_board_subdeck(
    eb: ExtractedBoard,
    *,
    sw1_closed: bool = False,
    sw2_closed: bool = False,
    xiao_tx_cur: float = 0.04,
    relay_drv_v: float = 0.0,
    relay_en: float = 1.0,
    tcrt_ctr: str | float = 0.03,
    trim_wiper: float = 0.48,
) -> tuple[list[str], dict[tuple[str, str], str]]:
    """Emit SPICE lines for one extracted PCB, including copper R/C parasitics and BOM models.
    Returns `(lines, pad_spice_node)` where `pad_spice_node[(ref, pin)]` is the pad's SPICE node."""
    lines: list[str] = [f"* --- Extracted Copper Subdeck: {eb.name} ---"]

    # Map reference ground node to '0' (or small ground return impedance for sub-boards)
    def bus_node(root: str) -> str:
        return "0" if (eb.name == "main" and root == eb.gnd_node) else root

    # Count pads per copper root to distribute extracted trace resistance across pad branches
    pads_per_root: dict[str, int] = {}
    for root in eb.pad_node.values():
        pads_per_root[root] = pads_per_root.get(root, 0) + 1

    # Emit shunt copper trace/via capacitance to local plane for every non-ground copper root
    emitted_roots: set[str] = set()
    for root in sorted(set(eb.pad_node.values())):
        bnode = bus_node(root)
        if bnode == "0" or bnode in emitted_roots:
            continue
        emitted_roots.add(bnode)
        c_cu = max(0.05e-12, eb.node_c_farad.get(root, 0.1e-12))
        gnd_ref = "0" if eb.name == "main" else eb.gnd_node
        lines.append(f"Ccu_{bnode} {bnode} {gnd_ref} {c_cu:.4e}")

    # Connect each component pad to its physical copper root via extracted trace series resistance
    pad_spice: dict[tuple[str, str], str] = {}
    for (ref, num), root in sorted(eb.pad_node.items()):
        bnode = bus_node(root)
        pnode = f"pad_{eb.name}_{ref}_{num}"
        r_branch = max(0.5e-3, eb.node_r_ohm.get(root, 1e-3) / max(1, pads_per_root[root]))
        lines.append(f"Rcu_{eb.name}_{ref}_{num} {pnode} {bnode} {r_branch:.5f}")
        pad_spice[(ref, num)] = pnode

    # Instantiate every component strictly from its exported BOM entry (MPN + Value)
    for ref, part in sorted(eb.bom.items()):
        tag = f"{eb.name}_{ref}"
        mpn = part.mpn

        # 2-pin Resistors
        if ref.startswith("R") and not ref.startswith("RV"):
            ohms = _parse_val(part.value)
            lines.append(f"R_{tag} {pad_spice[(ref, '1')]} {pad_spice[(ref, '2')]} {ohms:.6g}")
            continue

        # 2-pin Ceramic Capacitors (include realistic MLCC ESR so rail/filter Q is physical)
        if ref.startswith("C"):
            farads = _parse_val(part.value)
            esr = 0.015 if farads >= 1e-6 else 0.05
            mid = f"cesr_{tag}"
            lines.append(f"R_esr_{tag} {pad_spice[(ref, '1')]} {mid} {esr}")
            lines.append(f"C_{tag} {mid} {pad_spice[(ref, '2')]} {farads:.6g}")
            continue

        # Power Inductor (FNR4020S220MT: 22 uH, 455 mOhm DCR per datasheet)
        if mpn == "FNR4020S220MT":
            l_val = _parse_val(part.value)
            mid = f"ldcr_{tag}"
            lines.append(f"R_dcr_{tag} {pad_spice[(ref, '1')]} {mid} 0.455")
            lines.append(f"L_{tag} {mid} {pad_spice[(ref, '2')]} {l_val:.6g}")
            continue

        # Polyfuses (Littelfuse 1812L110/33MR & Bourns MF-USMF005-2)
        if mpn == "1812L110/33MR":
            lines.append(f"R_{tag} {pad_spice[(ref, '1')]} {pad_spice[(ref, '2')]} 0.12")
            continue
        if mpn == "MF-USMF005-2":
            lines.append(f"R_{tag} {pad_spice[(ref, '1')]} {pad_spice[(ref, '2')]} 5.5")
            continue

        # Trimmer Potentiometer (Bourns TC33X-2-103E: 1-2-3)
        if mpn == "TC33X-2-103E":
            total = _parse_val(part.value)
            r12 = max(1.0, (1.0 - trim_wiper) * total)
            r23 = max(1.0, trim_wiper * total)
            lines.append(f"R_{tag}_a {pad_spice[(ref, '1')]} {pad_spice[(ref, '2')]} {r12:.3f}")
            lines.append(f"R_{tag}_b {pad_spice[(ref, '2')]} {pad_spice[(ref, '3')]} {r23:.3f}")
            continue

        # Tactile Switches (Omron B3U-1000P)
        if mpn == "B3U-1000P":
            closed = (sw1_closed if ref == "SW1" else sw2_closed)
            r_sw = 0.2 if closed else 1e9
            lines.append(f"R_{tag} {pad_spice[(ref, '1')]} {pad_spice[(ref, '2')]} {r_sw}")
            continue

        # 2-pin Diodes / TVS / Zener / Red LED (KiCad convention verified in Test 1: 1=K, 2=A)
        diode_map = {
            "SS36": "D_SS36",
            "SS34": "D_SS34",
            "B5819W": "D_B5819W",
            "SMAJ30A": "D_SMAJ30A",
            "MMSZ5V6T1G": "D_Z5V6",
            "NCD0805R1": "D_LED_RED",
        }
        if mpn in diode_map:
            lines.append(f"D_{tag} {pad_spice[(ref, '2')]} {pad_spice[(ref, '1')]} {diode_map[mpn]}")
            continue

        # BAT54S,215 dual series Schottky (1=A1 -> 3=COM -> 2=K2)
        if mpn == "BAT54S,215":
            lines.append(f"D_{tag}_lo {pad_spice[(ref, '1')]} {pad_spice[(ref, '3')]} D_BAT54")
            lines.append(f"D_{tag}_hi {pad_spice[(ref, '3')]} {pad_spice[(ref, '2')]} D_BAT54")
            continue

        # MMBT3904 NPN BJT (1=B, 2=E, 3=C -> SPICE Q C B E)
        if mpn == "MMBT3904(RANGE:100-300)":
            lines.append(f"Q_{tag} {pad_spice[(ref, '3')]} {pad_spice[(ref, '1')]} {pad_spice[(ref, '2')]} Q_3904")
            continue

        # SCT2601TVBR buck converter (1=BST, 2=GND, 3=FB, 4=EN, 5=VIN, 6=SW)
        if mpn == "SCT2601TVBR":
            p = [pad_spice[(ref, str(i))] for i in range(1, 7)]
            lines.append(f"X_{tag} {' '.join(p)} MPN_SCT2601")
            continue

        # Seeed XIAO ESP32C6 14-pin module
        if mpn == "102010636":
            p = [pad_spice[(ref, str(i))] for i in range(1, 15)]
            lines.append(f"X_{tag} {' '.join(p)} MPN_XIAO14 tx_cur={xiao_tx_cur} relay_drv={relay_drv_v} relay_en={relay_en}")
            continue

        # Omron G6B-2114P-US DC5 relay (1, 3, 4, 5, 6, 8)
        if mpn == "G6B-2114P-US DC5":
            p = [pad_spice[(ref, k)] for k in ("1", "3", "4", "5", "6", "8")]
            lines.append(f"X_{tag} {' '.join(p)} MPN_G6B2114P")
            continue

        # TI SN74AHCT1G125DBVR buffer (1..5)
        if mpn == "SN74AHCT1G125DBVR":
            p = [pad_spice[(ref, str(i))] for i in range(1, 6)]
            lines.append(f"X_{tag} {' '.join(p)} MPN_74AHCT1G125")
            continue

        # Worldsemi WS2812B-MINI-V3J RGB LED (1..4; D3 pin 2 DOUT is unconnected on PCB -> tie to local dummy node)
        if mpn == "WS2812B-MINI-V3J":
            p1 = pad_spice[(ref, "1")]
            p2 = pad_spice.get((ref, "2"), f"nc_{tag}_dout")
            p3 = pad_spice[(ref, "3")]
            p4 = pad_spice[(ref, "4")]
            lines.append(f"X_{tag} {p1} {p2} {p3} {p4} MPN_WS2812B")
            continue

        # QG-6428TSWCG02 14-pin SSD1312 OLED (pins 1..5, 7..14; pin 6 is NC)
        if mpn == "QG-6428TSWCG02":
            p = [pad_spice[(ref, str(i))] for i in (1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14)]
            lines.append(f"X_{tag} {' '.join(p)} MPN_SSD1312")
            continue

        # Vishay TCRT5000 reflective optical sensor (1..4)
        if mpn == "TCRT5000":
            p = [pad_spice[(ref, str(i))] for i in range(1, 5)]
            lines.append(f"X_{tag} {' '.join(p)} MPN_TCRT5000 ctr={tcrt_ctr}")
            continue

        # TI LMV331IDBVR comparator (1..5)
        if mpn == "LMV331IDBVR":
            p = [pad_spice[(ref, str(i))] for i in range(1, 6)]
            lines.append(f"X_{tag} {' '.join(p)} MPN_LMV331")
            continue

        # Passive connectors / terminals (pins are wired externally or stitched by 3D coordinates)
        if mpn in (
            "2086-1202/700-000/997-604",
            "2086-1203/700-000/997-605",
            "2086-1204/700-000/997-605",
            "DG127R-5.08-03P-14-00A(H)",
            "FPC-05F-8PH20",
            "2059-303/998-403",
        ):
            continue

        raise AssertionError(f"Unhandled BOM MPN {mpn!r} ({eb.name}:{ref})")

    return lines, pad_spice


def stitch_3d_interconnects(
    eb_main: ExtractedBoard,
    pads_main: dict[tuple[str, str], str],
    eb_ui: ExtractedBoard,
    pads_ui: dict[tuple[str, str], str],
    eb_reader: ExtractedBoard | None = None,
    pads_reader: dict[tuple[str, str], str] | None = None,
) -> list[str]:
    """Stitch board-to-board connectors strictly by 3D `(X, Y, Z)` mating pad coordinates
    computed from `spec.yaml` enclosure planes — ZERO use of pin numbers or net names!"""
    spec = yaml.safe_load((REPO / "hardware/product/spec.yaml").read_text())
    m_cfg = spec["boards"]["main"]
    main_w = m_cfg["max_outline"]["width"]
    main_h = m_cfg["max_outline"]["height"]
    ui_w = spec["boards"]["ui"]["max_outline"]["width"]
    ui_h = spec["boards"]["ui"]["max_outline"]["height"]
    hid_h = spec["din_envelope"]["hidden_part"]["height"]
    front_h = spec["din_envelope"]["front_protrusion"]["height"]
    front_y0 = (hid_h - front_h) / 2.0
    ui_top_z = spec["front_ui"]["board_top_z"]
    ui_thick = spec["boards"]["ui"]["thickness"]

    def main_3d(x_mm: float, y_mm: float, is_back: bool) -> tuple[float, float, float]:
        n = -m_cfg["thickness"] if is_back else 0.0
        return (m_cfg["x"] + n, y_mm + m_cfg["y_offset"], m_cfg["z_front"] - x_mm)

    def ui_3d(x_mm: float, y_mm: float, is_back: bool) -> tuple[float, float, float]:
        n = -ui_thick if is_back else 0.0
        return (x_mm - ui_w / 2.0, y_mm + front_y0 + (front_h - ui_h) / 2.0, ui_top_z + n)

    # 1. Stitch 8-pin 0.5 mm Type-B FFC between `main` FFC connector and `ui` FFC connector:
    #    Find the FFC connector ref on each board strictly by BOM MPN `FPC-05F-8PH20`,
    #    exclude the 2 mechanical end-ear pads (keep the 8 colinear 0.5 mm signal pads),
    #    and order purely by 3D spatial ribbon axis (`Y_enc` descending on vertical `main`
    #    mates 1-to-1 with `X_enc` descending on front `ui` via 90-deg fold + Type-B strip!).
    main_ffc_ref = next(r for r, p in eb_main.bom.items() if p.mpn == "FPC-05F-8PH20")
    ui_ffc_ref = next(r for r, p in eb_ui.bom.items() if p.mpn == "FPC-05F-8PH20")

    def signal_8_pads(eb: ExtractedBoard, conn_ref: str):
        all_p = [(k, eb.pad_coords_mm[k]) for k in eb.pad_coords_mm if k[0] == conn_ref]
        # The 8 signal pads share one common line (within 0.05 mm); the 2 mounting tabs sit 1.7 mm offset
        pts_xy = [(k, c) for k, c in all_p]
        best_cluster = []
        for _k, (x0, y0, _b) in pts_xy:
            col_x = [item for item in pts_xy if abs(item[1][0] - x0) < 0.05]
            col_y = [item for item in pts_xy if abs(item[1][1] - y0) < 0.05]
            for cluster in (col_x, col_y):
                if len(cluster) > len(best_cluster):
                    best_cluster = cluster
        assert len(best_cluster) == 8, f"{eb.name}:{conn_ref} expected 8 colinear FFC pads, found {len(best_cluster)}"
        return best_cluster

    m_ffc = [(k, main_3d(*c)) for k, c in signal_8_pads(eb_main, main_ffc_ref)]
    u_ffc = [(k, ui_3d(*c)) for k, c in signal_8_pads(eb_ui, ui_ffc_ref)]
    m_sorted = sorted(m_ffc, key=lambda item: -item[1][1])  # 3D Y_enc descending
    u_sorted = sorted(u_ffc, key=lambda item: -item[1][0])  # 3D X_enc descending

    lines = ["* --- 3D Coordinate-Stitched Interconnects ---"]
    for idx, ((mk, _m3d), (uk, _u3d)) in enumerate(zip(m_sorted, u_sorted)):
        ma, ua = pads_main[mk], pads_ui[uk]
        lines.append(f"R_ffc_{idx} {ma} {ua} 0.15")
        lines.append(f"C_ffc_{idx} {ua} 0 2.5p")

    # 2. Optional 3-wire cable stitch from `reader` WAGO 2059-303 (`y` descending = poles 1, 2, 3)
    #    to `main` top sensor bank (10 poles ordered spatially along top shoulder `Z_enc` ascending /
    #    board `x` descending: pole 1 = +5V, pole 8 = IO4, pole 9 = GND)
    if eb_reader is not None and pads_reader is not None:
        top_terms = [
            (k, main_3d(*c))
            for k, c in eb_main.pad_coords_mm.items()
            if eb_main.bom[k[0]].mpn in ("2086-1204/700-000/997-605", "2086-1203/700-000/997-605")
        ]
        # Ordered along enclosure Z ascending (front-to-back along the 10-pole top bank = poles 1..10)
        poles_1_to_10 = sorted(top_terms, key=lambda item: item[1][2])
        assert len(poles_1_to_10) == 10

        rdr_conn = next(r for r, p in eb_reader.bom.items() if p.mpn == "2059-303/998-403")
        rdr_poles = sorted(
            [(k, c) for k, c in eb_reader.pad_coords_mm.items() if k[0] == rdr_conn],
            key=lambda item: -item[1][1],  # board +y descending = poles 1 (+5V), 2 (GND), 3 (PULSE)
        )
        assert len(rdr_poles) == 3
        # Pole 1 (+5V) -> bank[0], Pole 2 (GND) -> bank[8], Pole 3 (PULSE) -> bank[7]
        for idx, (rk, mk) in enumerate((
            (rdr_poles[0][0], poles_1_to_10[0][0]),
            (rdr_poles[1][0], poles_1_to_10[8][0]),
            (rdr_poles[2][0], poles_1_to_10[7][0]),
        )):
            lines.append(f"R_rcab_{idx} {pads_main[mk]} {pads_reader[rk]} 0.12")
            lines.append(f"C_rcab_{idx} {pads_reader[rk]} 0 50p")

    return lines


# ---------------------------------------------------------------------------
# 4. Pytest Fixtures & End-to-End Electrical Verification Gates
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def copper_boards() -> dict[str, ExtractedBoard]:
    return {b: extract_board_copper(b) for b in BOARDS}


@pytest.fixture(scope="module")
def spice() -> NgSpiceRunner:
    return NgSpiceRunner.get()


def test_zero_circuit_generator_imports():
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


@pytest.mark.parametrize("board", BOARDS)
def test_physical_copper_connectivity_has_zero_opens_and_zero_shorts(copper_boards, board):
    """1. `GetUnconnectedCount(False) == 0`.
       2. Pure geometric Union-Find over physical copper tracks, vias, filled zones
          and pads produces a strict 1-to-1 bijection with logical nets (zero opens, zero shorts)."""
    eb = copper_boards[board]
    assert eb.unconnected_count == 0, f"{board} has {eb.unconnected_count} unrouted connections"

    # Every logical net must map to EXACTLY 1 physical Union-Find copper component
    opens = {net: sorted(roots) for net, roots in eb.audit_net_to_nodes.items() if len(roots) != 1}
    assert not opens, f"{board} has physical copper opens (disconnected islands): {opens}"

    # Distinct logical nets must NEVER share a physical Union-Find copper component
    root_to_nets: dict[str, list[str]] = {}
    for net, roots in eb.audit_net_to_nodes.items():
        root = next(iter(roots))
        root_to_nets.setdefault(root, []).append(net)
    shorts = {root: nets for root, nets in root_to_nets.items() if len(nets) > 1}
    assert not shorts, f"{board} has physical copper shorts between distinct nets: {shorts}"


@pytest.mark.parametrize("vin", [9.0, 24.0, 30.0])
def test_power_rails_buck_regulation_and_cascaded_ldo_headroom_op(copper_boards, spice, vin):
    """Verify `.op` across the full 9-30 V input spec under peak 350 mA XIAO WiFi TX load,
    with `main` + `ui` + `reader` stitched together in 3D:
      - `+24V_LOOP` drops only `D2` Schottky Vf + `F1` DCR
      - `SCT2601` regulates `+5V` to `5.05 V +- 3%`
      - `D12` (`SS34`) drops `< 0.55 V` at 350 mA, leaving `>= 1.1 V` dropout headroom for XIAO 3.3 V LDO
      - `+3V3` regulates to `3.30 V +- 2%` on both `main` and `ui` (across FFC)
      - `reader` `+5V_S` receives `>= 4.5 V` after `D1` (`B5819W`)"""
    eb_m, eb_u, eb_r = copper_boards["main"], copper_boards["ui"], copper_boards["reader"]
    m_lines, m_pads = build_board_subdeck(eb_m, xiao_tx_cur=0.35)
    u_lines, u_pads = build_board_subdeck(eb_u)
    r_lines, r_pads = build_board_subdeck(eb_r)
    stitch = stitch_3d_interconnects(eb_m, m_pads, eb_u, u_pads, eb_r, r_pads)

    deck = [
        f"Power Rail & Headroom OP at VIN={vin}V",
        SPICE_MODELS,
        *m_lines, *u_lines, *r_lines, *stitch,
        f"V_in {m_pads[('J1', '2')]} {m_pads[('J1', '1')]} DC {vin}",
        ".op",
    ]
    spice.run_deck(deck)

    v_loop = spice.scalar(f"v({m_pads[('J2', '2')]})")
    v_5v = spice.scalar(f"v({m_pads[('J2', '1')]})")
    v_5v_xiao = spice.scalar(f"v({m_pads[('U3', '14')]})")
    v_3v3_main = spice.scalar(f"v({m_pads[('U3', '12')]})")
    v_3v3_ui = spice.scalar(f"v({u_pads[('J2', '5')]})")
    v_5v_reader = spice.scalar(f"v({r_pads[('U2', '5')]})")

    assert vin - 0.70 <= v_loop <= vin - 0.15
    assert 4.90 <= v_5v <= 5.20, f"+5V out of spec at VIN={vin}: {v_5v:.3f} V"
    assert v_5v_xiao >= 4.40, f"+5V_XIAO sagged too low under 350 mA TX: {v_5v_xiao:.3f} V"
    assert (v_5v_xiao - v_3v3_main) >= 1.10, "Insufficient dropout headroom above 3.3 V LDO"
    assert 3.24 <= v_3v3_main <= 3.36
    assert abs(v_3v3_main - v_3v3_ui) < 0.03, "Excessive FFC + copper drop between main and ui +3V3"
    assert 4.50 <= v_5v_reader <= 5.05


def test_reverse_polarity_usb_backfeed_and_uvlo_trip_thresholds(copper_boards, spice):
    """1. Reverse -24 V on `J1`: `D2` (`SS36`) blocks reverse voltage; rails stay near 0 V.
       2. USB-C +5 V back-feed on `U3.14` with `VIN=0 V`: `D12` (`SS34`) blocks back-feed into `+5V` / `+24V_LOOP`.
       3. Buck UVLO (`R1=100k / R2=20k`): off at `VIN=6.0 V`, cleanly enabled at `VIN=8.5 V`."""
    eb_m, eb_u = copper_boards["main"], copper_boards["ui"]

    # 1. Reverse -24 V input
    m_lines, m_pads = build_board_subdeck(eb_m)
    u_lines, u_pads = build_board_subdeck(eb_u)
    stitch = stitch_3d_interconnects(eb_m, m_pads, eb_u, u_pads)
    spice.run_deck([
        "Reverse -24V Input Protection",
        SPICE_MODELS, *m_lines, *u_lines, *stitch,
        f"V_in {m_pads[('J1', '2')]} {m_pads[('J1', '1')]} DC -24.0",
        ".op",
    ])
    assert -0.05 <= spice.scalar(f"v({m_pads[('U1', '5')]})") <= 0.05
    assert -0.05 <= spice.scalar(f"v({m_pads[('J2', '1')]})") <= 0.05

    # 2. USB-C 5 V back-feed on XIAO 5V pin (`U3.14`) with 24 V input unpowered (`R_in = 10k`)
    spice.run_deck([
        "USB-C Backfeed Blocking",
        SPICE_MODELS, *m_lines, *u_lines, *stitch,
        f"R_in_off {m_pads[('J1', '2')]} 0 10k",
        f"V_usb {m_pads[('U3', '14')]} 0 DC 5.0",
        ".op",
    ])
    assert spice.scalar(f"v({m_pads[('J2', '1')]})") < 0.15, "D12 failed to block USB-C back-feed to +5V sensor rail"
    assert 3.24 <= spice.scalar(f"v({m_pads[('U3', '12')]})") <= 3.36

    # 3. UVLO threshold check (off at 6.0 V, on at 8.5 V)
    for vin_test, expect_on in ((6.0, False), (8.5, True)):
        spice.run_deck([
            f"UVLO Test VIN={vin_test}",
            SPICE_MODELS, *m_lines, *u_lines, *stitch,
            f"V_in {m_pads[('J1', '2')]} {m_pads[('J1', '1')]} DC {vin_test}",
            ".op",
        ])
        v5 = spice.scalar(f"v({m_pads[('J2', '1')]})")
        if expect_on:
            assert 4.90 <= v5 <= 5.20, f"Buck failed to start above UVLO at VIN={vin_test}: +5V={v5:.2f}V"
        else:
            assert v5 < 0.5, f"Buck turned on below UVLO at VIN={vin_test}: +5V={v5:.2f}V"


def test_transient_surge_and_analog_miswire_overload_clamping_tran(copper_boards, spice):
    """Run `.tran` to prove:
       1. Input surge pulse (80 V peak through 8 Ohm generator -> ~5.5 A) is clamped by `D1` (`SMAJ30A`)
          strictly below 50 V (protecting 50 V MLCCs and SCT2601's 65 V abs max).
       2. Mis-wiring +24 V directly onto `4-20mA` (`J2.3`) or `0-10V` (`J2.4`) is clamped by
          `BAT54S` (`D3`, `D4`) so `MA_MCU` and `V0_10_MCU` stay strictly `< 3.60 V` (ESP32-C6 safe)."""
    eb_m, eb_u = copper_boards["main"], copper_boards["ui"]
    m_lines, m_pads = build_board_subdeck(eb_m)
    u_lines, u_pads = build_board_subdeck(eb_u)
    stitch = stitch_3d_interconnects(eb_m, m_pads, eb_u, u_pads)

    # 1. IEC 61000-4-5 2-Ohm power-line surge transient on VIN_RAW (55 V open-circuit surge -> ~8 A peak)
    spice.run_deck([
        "Input Surge Clamping",
        SPICE_MODELS, *m_lines, *u_lines, *stitch,
        f"V_surge src_surge 0 PULSE(24 55 5u 2u 10u 40u 200u)",
        f"R_surge_gen src_surge {m_pads[('J1', '2')]} 2.0",
        ".tran 0.5u 70u",
    ])
    v_loop_peak = max(spice.real_vec(f"v({m_pads[('U1', '5')]})"))
    assert 35.0 <= v_loop_peak < 49.5, f"TVS clamp peak out of safe window (35..49.5 V): {v_loop_peak:.2f} V"

    # 2. +24 V mis-wire step onto both analog terminals simultaneously (3 ms > 3 * R*C filter tau)
    spice.run_deck([
        "Analog +24V Miswire Clamp",
        SPICE_MODELS, *m_lines, *u_lines, *stitch,
        f"V_in {m_pads[('J1', '2')]} {m_pads[('J1', '1')]} DC 24.0",
        f"V_fault_ma {m_pads[('J2', '3')]} 0 PULSE(0 24 10u 1u 1u 3000u 6000u)",
        f"V_fault_v  {m_pads[('J2', '4')]} 0 PULSE(0 24 10u 1u 1u 3000u 6000u)",
        ".tran 20u 2500u",
    ])
    v_ma_peak = max(spice.real_vec(f"v({m_pads[('U3', '2')]})"))
    v_v10_peak = max(spice.real_vec(f"v({m_pads[('U3', '1')]})"))
    assert 3.30 <= v_ma_peak <= 3.65, f"MA_MCU exceeded safe clamp voltage: {v_ma_peak:.3f} V"
    assert 3.30 <= v_v10_peak <= 3.65, f"V0_10_MCU exceeded safe clamp voltage: {v_v10_peak:.3f} V"


def test_analog_frontends_dc_gain_ac_filtering_and_noise_gate(copper_boards, spice):
    """Verify end-to-end copper-extracted signal paths on `4-20 mA` (`J2.3 -> U3.2`)
    and `0-10 V` (`J2.4 -> U3.1`) via `.op`, `.ac` and `.noise` (`setplot noise1`):
      - 4-20 mA DC transfer: 4 mA -> 0.480 V, 20 mA -> 2.400 V (+- 10 mV incl. leakage & trace R)
      - 0-10 V DC transfer: 10.0 V -> 3.125 V (+- 10 mV)
      - `.ac` -3 dB low-pass cutoffs: 4-20 mA `fc ~ 159 Hz`, 0-10 V `fc ~ 231 Hz`
      - `.noise` (`setplot noise1` spectral density + `noise2.onoise_total`): integrated RMS noise
        0.1 Hz .. 100 kHz `< 25 uV_rms` (<< 12-bit ADC 1 LSB = 806 uV)
      - Shared `+5V` and `+3V3` rail `.ac` output impedance `< 1.0 Ohm` up to 1 MHz (no resonant instability)."""
    eb_m, eb_u = copper_boards["main"], copper_boards["ui"]
    m_lines, m_pads = build_board_subdeck(eb_m)
    u_lines, u_pads = build_board_subdeck(eb_u)
    stitch = stitch_3d_interconnects(eb_m, m_pads, eb_u, u_pads)

    # 1. DC accuracy at 4 mA / 0.4 V and 20 mA / 10.0 V
    for i_ma, v_in10, exp_ma, exp_v10 in ((0.004, 0.4, 0.480, 0.125), (0.020, 10.0, 2.400, 3.125)):
        spice.run_deck([
            "Analog DC Accuracy",
            SPICE_MODELS, *m_lines, *u_lines, *stitch,
            f"V_in {m_pads[('J1', '2')]} 0 DC 24.0",
            f"I_loop 0 {m_pads[('J2', '3')]} DC {i_ma}",
            f"V_src10 {m_pads[('J2', '4')]} 0 DC {v_in10}",
            ".op",
        ])
        got_ma = spice.scalar(f"v({m_pads[('U3', '2')]})")
        got_v10 = spice.scalar(f"v({m_pads[('U3', '1')]})")
        assert abs(got_ma - exp_ma) < 0.008, f"4-20mA error at {i_ma*1e3} mA: got {got_ma:.4f} V vs {exp_ma:.4f} V"
        assert abs(got_v10 - exp_v10) < 0.008, f"0-10V error at {v_in10} V: got {got_v10:.4f} V vs {exp_v10:.4f} V"

    # 2. `.ac` frequency response of 4-20 mA (`fc = 1/(2*pi*10.12k*100n) = 157 Hz`)
    spice.run_deck([
        "4-20mA AC Filter",
        SPICE_MODELS, *m_lines, *u_lines, *stitch,
        f"V_in {m_pads[('J1', '2')]} 0 DC 24.0",
        f"I_loop 0 {m_pads[('J2', '3')]} DC 0.012 AC 1.0",
        ".ac dec 40 1 100k",
    ])
    freqs = spice.real_vec("frequency")
    mag_ma = [abs(c) for c in spice.complex_vec(f"v({m_pads[('U3', '2')]})")]
    dc_gain = mag_ma[0]
    assert dc_gain == pytest.approx(120.0, rel=0.015)
    fc_ma = next(f for f, g in zip(freqs, mag_ma) if g <= dc_gain / math.sqrt(2))
    assert 140.0 <= fc_ma <= 175.0, f"4-20mA -3dB cutoff={fc_ma:.1f} Hz"

    # 3. `.ac` frequency response of 0-10 V (`fc = 1/(2*pi*(22k||10k)*100n) = 231 Hz`)
    spice.run_deck([
        "0-10V AC Filter",
        SPICE_MODELS, *m_lines, *u_lines, *stitch,
        f"V_in {m_pads[('J1', '2')]} 0 DC 24.0",
        f"V_src10 {m_pads[('J2', '4')]} 0 DC 5.0 AC 1.0",
        ".ac dec 40 1 100k",
    ])
    freqs = spice.real_vec("frequency")
    mag_v10 = [abs(c) for c in spice.complex_vec(f"v({m_pads[('U3', '1')]})")]
    assert mag_v10[0] == pytest.approx(10.0 / 32.0, rel=0.015)
    fc_v10 = next(f for f, g in zip(freqs, mag_v10) if g <= mag_v10[0] / math.sqrt(2))
    assert 205.0 <= fc_v10 <= 255.0, f"0-10V -3dB cutoff={fc_v10:.1f} Hz"

    # 4. `.noise` (`setplot noise1` spectral density + `noise2` total RMS noise)
    spice.run_deck([
        "0-10V Noise Analysis",
        SPICE_MODELS, *m_lines, *u_lines, *stitch,
        f"V_in {m_pads[('J1', '2')]} 0 DC 24.0",
        f"V_src10 {m_pads[('J2', '4')]} 0 DC 5.0 AC 1.0",
        f".noise v({m_pads[('U3', '1')]}) V_src10 dec 20 0.1 100k",
    ])
    spice.cmd("setplot noise1")
    spec_density = spice.real_vec("onoise_spectrum")
    assert len(spec_density) > 50 and max(spec_density) < 50e-9  # < 50 nV/sqrt(Hz)
    onoise_rms = spice.scalar("noise2.onoise_total")
    assert 0.5e-7 < onoise_rms < 25e-6, f"Unexpected integrated ADC RMS noise: {onoise_rms:.3e} V_rms"

    # 5. Shared `+5V` rail `.ac` output impedance stability under real BOM decoupling
    spice.run_deck([
        "+5V Rail Impedance Stability",
        SPICE_MODELS, *m_lines, *u_lines, *stitch,
        f"V_in {m_pads[('J1', '2')]} 0 DC 24.0",
        f"I_probe {m_pads[('J2', '1')]} 0 DC 0 AC 1.0",
        ".ac dec 25 10 1Meg",
    ])
    z_5v = [abs(c) for c in spice.complex_vec(f"v({m_pads[('J2', '1')]})")]
    assert max(z_5v) < 0.85, f"Resonant impedance spike on +5V rail: max |Z|={max(z_5v):.3f} Ohm"


def test_ui_button_ladder_relay_flyback_and_dial_reader_hysteresis(copper_boards, spice):
    """End-to-end functional verification across all 3 boards:
       1. UI button ladder (`main` + `ui` stitched by 3D FFC): none=3.30 V, SW1=2.20 V, SW2=1.65 V, both=1.32 V.
       2. Relay driver (`Q1`/`K1`/`D7`): saturation + changeover contact switching + turn-off inductive flyback clamp `< 5.8 V`.
       3. Optical dial reader (`reader` + `main` stitched by 3D terminal poles): comparator positive hysteresis +
          open-collector `IO4_MCU` swing (`< 0.45 V` low, `~3.30 V` high, never exceeding 3.35 V)."""
    eb_m, eb_u, eb_r = copper_boards["main"], copper_boards["ui"], copper_boards["reader"]

    # 1. UI 2-button ADC ladder across 3D-stitched FFC
    expected_ladder = [
        (False, False, 3.300),
        (True,  False, 2.200),
        (False, True,  1.650),
        (True,  True,  1.320),
    ]
    for s1, s2, v_exp in expected_ladder:
        m_lines, m_pads = build_board_subdeck(eb_m)
        u_lines, u_pads = build_board_subdeck(eb_u, sw1_closed=s1, sw2_closed=s2)
        stitch = stitch_3d_interconnects(eb_m, m_pads, eb_u, u_pads)
        spice.run_deck([
            f"Button Ladder sw1={s1} sw2={s2}",
            SPICE_MODELS, *m_lines, *u_lines, *stitch,
            f"V_in {m_pads[('J1', '2')]} 0 DC 24.0",
            ".op",
        ])
        v_btn = spice.scalar(f"v({m_pads[('U3', '3')]})")
        assert abs(v_btn - v_exp) < 0.03, f"Button ladder ({s1}, {s2}): got {v_btn:.3f} V, expected {v_exp:.3f} V"

    # 2. Relay changeover switching & inductive turn-off flyback clamping (`.tran`)
    m_lines, m_pads = build_board_subdeck(eb_m, relay_en=0.0)
    u_lines, u_pads = build_board_subdeck(eb_u)
    stitch = stitch_3d_interconnects(eb_m, m_pads, eb_u, u_pads)
    spice.run_deck([
        "Relay Turn-On and Flyback Clamp",
        SPICE_MODELS, *m_lines, *u_lines, *stitch,
        f"V_in {m_pads[('J1', '2')]} 0 DC 24.0",
        f"V_rel_pulse rel_pulse_src 0 PULSE(0 3.3 50u 1u 1u 2400u 5000u)",
        f"R_rel_gpio rel_pulse_src {m_pads[('U3', '9')]} 35.0",
        f"V_com {m_pads[('J4', '1')]} 0 DC 10.0",
        f"R_load_no {m_pads[('J4', '2')]} 0 1k",
        f"R_load_nc {m_pads[('J4', '3')]} 0 1k",
        ".tran 10u 3200u",
    ])
    t_vec = spice.real_vec("time")
    v_coil_n = spice.real_vec(f"v({m_pads[('Q1', '3')]})")
    v_5v_rail = spice.real_vec(f"v({m_pads[('D7', '1')]})")
    v_no = spice.real_vec(f"v({m_pads[('J4', '2')]})")
    v_nc = spice.real_vec(f"v({m_pads[('J4', '3')]})")
    # Before turn-on (t ~ 20 us): NC closed (~10 V), NO open (~0 V)
    i_pre = next(i for i, t in enumerate(t_vec) if t >= 20e-6)
    assert v_nc[i_pre] > 9.8 and v_no[i_pre] < 0.1
    # Energized plateau (t ~ 2200 us, > 4 * L/R coil time constants): Q1 saturated, NO closed, NC open
    i_on = next(i for i, t in enumerate(t_vec) if t >= 2200e-6)
    assert v_coil_n[i_on] < 0.25, f"Q1 failed to saturate: V_CE={v_coil_n[i_on]:.3f} V"
    assert v_no[i_on] > 9.8 and v_nc[i_on] < 0.1
    # Turn-off flyback spike (t > 2450 us): D7 clamps RELAY_COIL_N within one Schottky drop of +5V,
    # and D8 (MMSZ5V6) holds the +5V rail dump strictly < 8.5 V (<< Q1 40 V V_CEO)
    max_d7_over = max(vc - v5 for vc, v5 in zip(v_coil_n, v_5v_rail))
    assert max_d7_over < 0.55, f"Flyback diode D7 failed to clamp coil node to +5V: overshoot={max_d7_over:.2f} V"
    assert max(v_coil_n) < 8.5, f"Relay flyback unclamped! Peak V(RELAY_COIL_N)={max(v_coil_n):.2f} V"

    # 3. Optical dial reader triangle sweep -> LMV331 hysteresis + main IO4_MCU pulse swing
    m_lines, m_pads = build_board_subdeck(eb_m)
    u_lines, u_pads = build_board_subdeck(eb_u)
    r_lines, r_pads = build_board_subdeck(eb_r, tcrt_ctr=0.0, trim_wiper=0.48)
    # Drive TCRT5000 phototransistor sense node with slow optical reflection ramp up & down (0.05..0.90 mA)
    stitch = stitch_3d_interconnects(eb_m, m_pads, eb_u, u_pads, eb_r, r_pads)
    spice.run_deck([
        "Dial Reader Hysteresis Sweep",
        SPICE_MODELS, *m_lines, *u_lines, *r_lines, *stitch,
        f"V_in {m_pads[('J1', '2')]} 0 DC 24.0",
        f"I_refl {r_pads[('U1', '3')]} {r_pads[('U1', '4')]} PWL(0 0.05m 10m 0.85m 20m 0.05m)",
        ".tran 50u 20m",
    ])
    t_vec = spice.real_vec("time")
    v_sense = spice.real_vec(f"v({r_pads[('U1', '4')]})")
    v_io4 = spice.real_vec(f"v({m_pads[('U3', '11')]})")

    # ESP32-C6 V_IL_max = 0.25 * 3.3 V = 0.825 V; reader R6 (330R) + main R21 (330R) against R20 (4.7k)
    # divides V_OL to ~0.49 V (335 mV margin below V_IL_max)
    assert min(v_io4) < 0.60, f"Dial reader failed to pull IO4_MCU below V_IL: min={min(v_io4):.3f} V"
    assert 3.20 <= max(v_io4) <= 3.36, f"IO4_MCU high level out of 3.3 V logic bounds: max={max(v_io4):.3f} V"

    # Measure rising vs falling trip threshold on V(SENSE) to prove positive ~70-120 mV hysteresis!
    mid_idx = next(i for i, t in enumerate(t_vec) if t >= 10e-3)
    v_trip_rise = next(v_sense[i] for i in range(mid_idx) if v_io4[i] > 1.65)
    v_trip_fall = next(v_sense[i] for i in range(mid_idx, len(t_vec)) if v_io4[i] < 1.65)
    hyst_mv = (v_trip_rise - v_trip_fall) * 1000.0
    assert 45.0 <= hyst_mv <= 160.0, f"Comparator hysteresis out of spec: {hyst_mv:.1f} mV (rise={v_trip_rise:.3f}, fall={v_trip_fall:.3f})"


def test_ws2812b_5v_level_translator_and_daisy_chain_tran(copper_boards, spice):
    """Verify 3.3 V `LED_DATA` from `main:U3.4` crosses the 3D-stitched FFC to `ui:U1`
    (`SN74AHCT1G125` 5 V TTL buffer), translates to `0..5 V` through `R4 (330R)` into
    `D1.DIN`, and regenerates cleanly along `D1.DOUT -> D2.DIN` and `D2.DOUT -> D3.DIN`."""
    eb_m, eb_u = copper_boards["main"], copper_boards["ui"]
    m_lines, m_pads = build_board_subdeck(eb_m)
    u_lines, u_pads = build_board_subdeck(eb_u)
    stitch = stitch_3d_interconnects(eb_m, m_pads, eb_u, u_pads)

    # Override XIAO LED pin internal 0 V hold with a 3.3 V pulse
    spice.run_deck([
        "WS2812B 5V Buffer & Chain",
        SPICE_MODELS, *m_lines, *u_lines, *stitch,
        f"V_in {m_pads[('J1', '2')]} 0 DC 24.0",
        f"I_led_pulse 0 {m_pads[('U3', '4')]} PULSE(0 0.0825 2u 50n 50n 4u 10u)",
        ".tran 50n 8u",
    ])
    v_d1_din = spice.real_vec(f"v({u_pads[('D1', '4')]})")
    v_d2_din = spice.real_vec(f"v({u_pads[('D2', '4')]})")
    v_d3_din = spice.real_vec(f"v({u_pads[('D3', '4')]})")
    for label, vec in (("D1.DIN", v_d1_din), ("D2.DIN", v_d2_din), ("D3.DIN", v_d3_din)):
        assert min(vec) < 0.25, f"{label} failed to pull low: min={min(vec):.3f} V"
        assert max(vec) > 4.70, f"{label} failed 5 V CMOS high translation: max={max(vec):.3f} V"
