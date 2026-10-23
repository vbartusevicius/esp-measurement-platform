"""Independent fit / retention / assemblability audit of the 1-DIN enclosure
against the real board outlines and component envelopes.

Uses the RELEASED base/cover STEP files (what you would print) plus the board
slabs and component boxes derived from hardware/build/<variant>/*/components_*.json
via mechanical/scripts/enclosure_features.py.

Checks:
  1. interference of every board slab / component box with base and cover
  2. clearance (min distance) of every component to the enclosure (< 0.3 mm flagged)
  3. retention: which enclosure features touch each board, per axis direction
  4. assemblability: sweep each board (with its parts) along candidate insertion
     directions and report the first colliding step
  6. display panel (real outline from spec.yaml) seating in the cover
  7. base/cover interference location (intended snap barbs vs real clashes)
Component heights come from components_*.json; parts that fall back to the
layout `heights.default` (e.g. 0.65 mm SK6805 LEDs listed as 1.2 mm) can show
false clashes - confirm against the datasheet height before reporting.

Run in the CAD container from the repo root:
  docker run --rm -v "$PWD":/work -w /work <cad-image> \
    "python3 .claude/skills/manufacturing-readiness-review/scripts/enclosure_fit_audit.py hardware/releases/v1/enclosure"
A directory with box_base/box_lid files is audited as the wall-mount box
(mechanical/scripts/build_box_enclosure.py: UI board rotated to face +x, main
board dropped in along -x before the lid); the panel check (6) is then covered
by the OLED panel envelope in check 1.
"""

import sys
from pathlib import Path

import cadquery as cq
import numpy as np

REPO = Path.cwd()
sys.path.insert(0, str(REPO / "mechanical/scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import enclosure_features as ef  # noqa: E402
from mesh_audit import read_stl  # noqa: E402


def box(b, grow=0.0):
    return cq.Workplane("XY").box(b["x1"] - b["x0"] + 2 * grow, b["y1"] - b["y0"] + 2 * grow, b["z1"] - b["z0"] + 2 * grow,
                                  centered=False).translate((b["x0"] - grow, b["y0"] - grow, b["z0"] - grow))


MESH = {}  # id(workplane) -> (M,3,3) triangles of the matching released STL


def mesh_inside(tris, pts, chunk=2000):
    """Ray-parity point-in-mesh test (vectorised Moller-Trumbore, skewed ray)."""
    d = np.array([1.0, 1.3e-3, 2.1e-3])
    v0, e1, e2 = tris[:, 0], tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    h = np.cross(d, e2)
    a = np.einsum("ij,ij->i", e1, h)
    ok = np.abs(a) > 1e-12
    v0, e1, e2, h, a = v0[ok], e1[ok], e2[ok], h[ok], a[ok]
    f = 1.0 / a
    out = np.zeros(len(pts), dtype=bool)
    for s in range(0, len(pts), chunk):
        p = pts[s:s + chunk, None, :]
        sv = p - v0[None]
        u = f * np.einsum("nmj,mj->nm", sv, h)
        q = np.cross(sv, e1[None])
        v = f * np.einsum("j,nmj->nm", d, q)
        t = f * np.einsum("mj,nmj->nm", e2, q)
        hit = (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-9)
        out[s:s + chunk] = hit.sum(1) % 2 == 1
    return out


def vol(a, b, pitch=0.2):
    """Overlap volume of solid `a` with box-like solid `b`.

    OCC booleans on imported STEP solids can silently return an empty result,
    so an empty boolean is cross-checked by sampling `b`'s bounding box against
    the released STL of `a` (registered in MESH)."""
    try:
        boolean = a.intersect(b).val().Volume()
    except Exception:
        boolean = 0.0
    if boolean > 1e-6 or id(a) not in MESH:
        return boolean
    tris = MESH[id(a)]
    bb = b.val().BoundingBox()
    lo = np.maximum([bb.xmin, bb.ymin, bb.zmin], tris.reshape(-1, 3).min(0))
    hi = np.minimum([bb.xmax, bb.ymax, bb.zmax], tris.reshape(-1, 3).max(0))
    if np.any(hi <= lo):
        return boolean
    sel = tris[(tris[:, :, 1].max(1) >= lo[1]) & (tris[:, :, 1].min(1) <= hi[1]) &
               (tris[:, :, 2].max(1) >= lo[2]) & (tris[:, :, 2].min(1) <= hi[2]) &
               (tris[:, :, 0].max(1) >= lo[0])]
    n = np.maximum(1, np.round((hi - lo) / pitch).astype(int))
    while n.prod() > 8000:
        n = np.maximum(1, (n / 1.3).astype(int))
    step = (hi - lo) / n
    grid = np.stack(np.meshgrid(*[lo[i] + (np.arange(n[i]) + 0.5) * step[i] for i in range(3)], indexing="ij"), -1)
    hits = mesh_inside(sel, grid.reshape(-1, 3)).sum()
    return max(boolean, float(hits * step.prod()))


def box_layout():
    """Board slabs, parts and insertion sweeps of the wall-mount box."""
    import build_box_enclosure as bx

    def ui_box(s):
        a, b = bx.point_to_box(s["x0"], s["y0"], s["z0"]), bx.point_to_box(s["x1"], s["y1"], s["z1"])
        return dict(s, ref="ui PCB", x0=min(a[0], b[0]), x1=max(a[0], b[0]), y0=min(a[1], b[1]), y1=max(a[1], b[1]),
                    z0=min(a[2], b[2]), z1=max(a[2], b[2]))
    boards = {"main": [dict(s, ref="main PCB") for s in ef.board_slabs("main")],
              "ui": [ui_box(s) for s in ef.board_slabs("ui")]}
    return boards, bx.MAIN_PARTS + bx.ui_parts_box(), (("from +x (front, before the lid)", (1, 0, 0)),)


def main(encl_dir):
    encl = Path(encl_dir)
    wall_box = (encl / "box_base.step").exists()
    names = {"base": "box_base", "cover": "box_lid"} if wall_box else {"base": "base", "cover": "cover"}
    shells = {}
    for name, stem in names.items():
        shells[name] = cq.importers.importStep(str(encl / f"{stem}.step"))
        MESH[id(shells[name])] = read_stl(encl / f"{stem}.stl")
    base, cover = shells["base"], shells["cover"]

    if wall_box:
        boards, parts, sweeps = box_layout()
    else:
        boards = {}
        for board in ef.SPEC["variants"][ef.VARIANT]["boards"]:
            boards[board] = [dict(s, ref=f"{board} PCB") for s in ef.board_slabs(board)]
        parts = ef.part_boxes()
        sweeps = (("from -x (left, open side)", (-1, 0, 0)), ("from +z (front, before cover)", (0, 0, 1)))

    print("== 1. Interference (board slabs + component boxes vs printed parts) ==")
    clashes = 0
    for name, shell in shells.items():
        for b in [s for v in boards.values() for s in v] + parts:
            v = vol(shell, box(b))
            if v > 0.01:
                clashes += 1
                tag = " (through-front part, expected)" if b.get("through_front") else ""
                print(f"  CLASH {b.get('board','')}:{b['ref']} x {name}: {v:.2f} mm3 "
                      f"box x[{b['x0']:.2f},{b['x1']:.2f}] y[{b['y0']:.2f},{b['y1']:.2f}] z[{b['z0']:.2f},{b['z1']:.2f}]{tag}")
    print(f"  -> {clashes} clashes")

    print("\n== 2. Tight clearances (< 0.3 mm, not touching) ==")
    for b in parts:
        bx = box(b).val()
        for name, shell in shells.items():
            d = bx.distance(shell.val())
            if 0 < d < 0.3:
                print(f"  {b['board']}:{b['ref']} to {name}: {d:.3f} mm")

    shift = 0.4
    print(f"\n== 3. Board retention: does each board (with its parts) hit the enclosure when shifted {shift} mm? ==")
    for board, slabs in boards.items():
        group = slabs + [p for p in parts if p["board"] == board and not p.get("through_front")
                         and not p["ref"].startswith("OLED")]
        for d, vec in (("-x", (-1, 0, 0)), ("+x", (1, 0, 0)), ("-y", (0, -1, 0)),
                       ("+y", (0, 1, 0)), ("-z", (0, 0, -1)), ("+z", (0, 0, 1))):
            hits = {}
            for b in group:
                moved = box(b).translate(tuple(c * shift for c in vec))
                for n, sh in shells.items():
                    v = vol(sh, moved, pitch=0.1) - vol(sh, box(b), pitch=0.1)
                    if v > 1e-3:
                        hits.setdefault(n, []).append(b["ref"])
            print(f"  {board} {d}: {'stopped by ' + str({n: sorted(set(r))[:4] for n, r in hits.items()}) if hits else 'FREE (nothing restrains this direction)'}")

    print("\n== 4. Assemblability sweeps of the main board + its parts into the base ==")
    main_items = boards["main"] + [p for p in parts if p["board"] == "main"]
    for label, vec in sweeps:
        blocked = False
        for t in (0.0, 1.0, 3.0, 8.0, 15.0, 30.0):
            hits = [f"{b['ref']}:{v:.1f}" for b in main_items
                    if (v := vol(base, box(b).translate(tuple(c * t for c in vec)), pitch=0.4)) > 0.05]
            blocked |= bool(hits) and t > 0
            print(f"  {label} offset {t:4.1f} mm: {'collides ' + ', '.join(hits) if hits else 'clear'}")
        print(f"  -> {label}: {'BLOCKED' if blocked else 'clear path'}")

    print("\n== 6. Display panel (real outline from spec front_ui.display.part) seating in the cover ==")
    import re
    m = re.search(r"\(([\d.]+) x ([\d.]+) x ([\d.]+) mm", ef.SPEC["front_ui"]["display"]["part"])
    if wall_box:
        print("  covered by the OLED panel envelope in check 1")
    elif m:
        w, h, t = map(float, m.groups())
        mod = ef.oled_module()
        inner = ef.TOTAL_D - ef.WALL
        for label, front in (("against front-wall inner face", inner),
                             ("glass flush with front face - only relevant if the panel is meant to pass through the window",
                              ef.TOTAL_D - 0.1),
                             ("in the 1.0 mm pocket (current design)", inner + 1.0)):
            p = {"x0": mod["cx"] - w / 2, "x1": mod["cx"] + w / 2, "y0": mod["cy"] - h / 2, "y1": mod["cy"] + h / 2,
                 "z0": front - t, "z1": front}
            v = vol(cover, box(p))
            print(f"  {w}x{h}x{t} panel, front at z={front:.2f} ({label}): {'CLASH ' + format(v, '.1f') + ' mm3' if v > 0.05 else 'fits'}")

    print("\n== 7. Base x cover overlap locations ==")
    ov = base.intersect(cover)
    for s in ov.solids().vals():
        bb = s.BoundingBox()
        print(f"  {s.Volume():.3f} mm3 at x[{bb.xmin:.2f},{bb.xmax:.2f}] y[{bb.ymin:.2f},{bb.ymax:.2f}] z[{bb.zmin:.2f},{bb.zmax:.2f}]")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "hardware/releases/v1/enclosure")
