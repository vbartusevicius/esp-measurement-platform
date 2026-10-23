"""Generic printability audit of released STL/STEP parts.

For every STL: triangle count, watertightness (each edge shared by exactly two
faces), connected bodies (a printed part must be ONE body unless it is meant
to print as loose pieces), volume and bounding box per body.
For STEP files: solid count per file and pairwise interference volumes
between files listed in --pairs (parts that are assembled together must not
overlap except where a snap overlap is intended).

Run inside the CAD container (numpy + cadquery):
  docker run --rm -v "$PWD":/work -w /work <cad-image> \
    "python3 .claude/skills/manufacturing-readiness-review/scripts/mesh_audit.py hardware/releases/v1"
"""

import argparse
import itertools
import struct
import sys
from pathlib import Path

import numpy as np


def read_stl(path):
    data = path.read_bytes()
    if data[:5] == b"solid" and b"facet" in data[:400]:
        tris = [list(map(float, line.split()[1:4])) for line in data.decode(errors="ignore").splitlines()
                if line.strip().startswith("vertex")]
        return np.array(tris, dtype=float).reshape(-1, 3, 3)
    n = struct.unpack("<I", data[80:84])[0]
    rec = np.frombuffer(data[84:84 + n * 50], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    return rec["v"].reshape(-1, 3, 3).astype(float)


def bodies(tris, decimals=4):
    verts, inv = np.unique(np.round(tris.reshape(-1, 3), decimals), axis=0, return_inverse=True)
    faces = inv.reshape(-1, 3)
    parent = np.arange(len(verts))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for f in faces:
        ra, rb, rc = find(f[0]), find(f[1]), find(f[2])
        parent[rb] = ra
        parent[find(rc)] = ra
    roots = np.array([find(v) for v in range(len(verts))])
    face_root = roots[faces[:, 0]]
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    open_edges = int((counts == 1).sum())
    nonmanifold = int((counts > 2).sum())
    out = []
    for r in np.unique(face_root):
        sel = tris[face_root == r]
        vol = float(np.einsum("ij,ij->i", sel[:, 0], np.cross(sel[:, 1], sel[:, 2])).sum() / 6.0)
        out.append({"faces": len(sel), "volume": abs(vol), "min": sel.reshape(-1, 3).min(0), "max": sel.reshape(-1, 3).max(0)})
    out.sort(key=lambda b: -b["volume"])
    return out, open_edges, nonmanifold


def audit_stl(path):
    tris = read_stl(path)
    parts, open_edges, nonmanifold = bodies(tris)
    status = "OK"
    if open_edges or nonmanifold:
        status = "NOT WATERTIGHT"
    if len(parts) > 1:
        status = (status + " + " if status != "OK" else "") + f"{len(parts)} SEPARATE BODIES"
    print(f"\n[{status}] {path}  tris={len(tris)} open_edges={open_edges} nonmanifold_edges={nonmanifold}")
    for i, b in enumerate(parts):
        mn, mx = b["min"], b["max"]
        print(f"   body {i}: vol={b['volume']:.1f} mm3 bbox=({mn[0]:.1f},{mn[1]:.1f},{mn[2]:.1f})..({mx[0]:.1f},{mx[1]:.1f},{mx[2]:.1f})"
              f" size={mx[0]-mn[0]:.1f}x{mx[1]-mn[1]:.1f}x{mx[2]-mn[2]:.1f}")
    return len(parts), open_edges + nonmanifold


def audit_step_pairs(files):
    import cadquery as cq
    shapes = {}
    for f in files:
        s = cq.importers.importStep(str(f))
        n = len(s.solids().vals())
        print(f"STEP {f}: {n} solid(s){'  <-- expected 1 per printed part' if n != 1 else ''}")
        shapes[f] = s
    for a, b in itertools.combinations(files, 2):
        v = shapes[a].intersect(shapes[b]).val().Volume() if shapes[a].intersect(shapes[b]).vals() else 0.0
        d = shapes[a].val().distance(shapes[b].val()) if v < 1e-6 else 0.0
        flag = "INTERFERENCE" if v > 0.01 else "ok"
        print(f"  [{flag}] {Path(a).name} x {Path(b).name}: overlap={v:.3f} mm3 min_gap={d:.3f} mm")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("release_dir")
    ap.add_argument("--pairs", nargs="*", default=None,
                    help="groups of STEP files assembled together, comma separated per group")
    args = ap.parse_args()
    root = Path(args.release_dir)
    bad = 0
    for stl in sorted(root.rglob("*.stl")):
        n, holes = audit_stl(stl)
        bad += (n > 1) + (holes > 0)
    if args.pairs:
        for group in args.pairs:
            print()
            audit_step_pairs([Path(p) for p in group.split(",")])
    print(f"\nSTL files with problems: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
