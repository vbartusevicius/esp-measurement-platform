"""Assembly drawings for hand soldering: where each part goes, even where the
silkscreen reference had to be hidden.

    python3 hardware/scripts/assembly_drawing.py <board> [out.pdf]

Writes a PDF (default hardware/build/<variant>/<board>/<board>_assembly.pdf):
one page per populated side (bottom mirrored, as seen from below) with every
part's body outline, its pads, a red pin-1 dot, and its reference and value;
parts of the same value share a colour. A last page lists the values with
their colour, quantity, side and references, so one value can be placed all
at once. Reads only the exported part boxes (components_<board>.json), the
parts list (parts.json) and the layout plan's outline.
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yaml
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Circle, Polygon, Rectangle

REPO = Path(__file__).resolve().parents[1].parent
sys.path.insert(0, str(REPO / "hardware/circuits"))
from product_spec import load_spec

VARIANT = load_spec()["active_variant"]
A4 = (8.27, 11.69)


def build(board):
    return REPO / "hardware/build" / VARIANT / board


def outline(board):
    frame = yaml.safe_load((REPO / "hardware/circuits/variants" / VARIANT / f"layout_{board}.yaml").read_text())["frame"]
    if frame.get("outline"):
        return [tuple(p) for p in frame["outline"]]
    w, h = frame["size"]["x"], frame["size"]["y"]
    return [(0, 0), (w, 0), (w, h), (0, h)]


def placements(board):
    """One entry per part: ref, value, part number, side, body box, pads."""
    comps = {c["ref"]: c for c in json.loads((build(board) / f"components_{board}.json").read_text())}
    parts = {p["ref"]: p for p in json.loads((build(board) / "parts.json").read_text())}
    out = []
    for ref, c in comps.items():
        p = parts.get(ref, {})
        out.append({"ref": ref, "value": c["value"], "mpn": p.get("mpn", ""), "lcsc": p.get("lcsc", ""),
                    "hand": p.get("assembly") == "hand", "side": c["side"], "bbox": c["bbox"],
                    "footprint": c["footprint"], "pads": c["pads"]})
    return sorted(out, key=lambda e: (e["side"], e["value"], e["ref"]))


def groups(items):
    """Parts that are the same thing to place: value + footprint -> colour index."""
    keys = sorted({(e["value"], e["footprint"]) for e in items})
    return {k: i for i, k in enumerate(keys)}


def colour(i):
    cmap = plt.get_cmap("tab20")
    return cmap(i % 20)


BIG_MM2 = 60.0   # bigger bodies (XIAO, relay, terminals) are outlines, drawn under the small parts


def area(e):
    b = e["bbox"]
    return (b["x1"] - b["x0"]) * (b["y1"] - b["y0"])


def short(value):
    """'2086-1203/700-000/997-605' -> '2086-1203'; long names cut to 16 characters."""
    return value.split("/")[0][:16]


def ref_order(ref):
    letters = ref.rstrip("0123456789")
    return letters, int(ref[len(letters):] or 0)


def size_label(footprint):
    for token in ("0402", "0603", "0805", "1206", "1210", "1812", "SOT-23-6", "SOT-23-5", "SOT-23", "TSOT-23-6",
                  "SMA", "SOD-123"):
        if token in footprint:
            return token
    return footprint.split("_")[0] if "_" in footprint else footprint


def side_page(pdf, board, side, items, colours):
    shape = outline(board)
    xs, ys = [p[0] for p in shape], [p[1] for p in shape]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    mirror = side == "back"

    def X(x):
        return (max(xs) - x + min(xs)) if mirror else x

    fig = plt.figure(figsize=A4)
    ax = fig.add_axes((0.06, 0.06, 0.88, 0.86))
    ax.set_aspect("equal")
    ax.axis("off")
    pad = 2.0
    ax.set_xlim(min(xs) - pad, max(xs) + pad)
    ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.add_patch(Polygon([(X(x), y) for x, y in shape], closed=True, fc="#f4f1e8", ec="black", lw=1.2))
    frame = ax.get_position()
    mm_per_inch = max((w + 2 * pad) / (A4[0] * frame.width), (h + 2 * pad) / (A4[1] * frame.height))
    pt_per_mm = 72 / mm_per_inch
    big = [e for e in items if area(e) > BIG_MM2]
    for e in sorted(big, key=area, reverse=True) + [e for e in items if area(e) <= BIG_MM2]:
        b = e["bbox"]
        x0, x1 = sorted((X(b["x0"]), X(b["x1"])))
        bw, bh = x1 - x0, b["y1"] - b["y0"]
        col = colour(colours[(e["value"], e["footprint"])])
        large = area(e) > BIG_MM2
        ax.add_patch(Rectangle((x0, b["y0"]), bw, bh, fc="none" if large else col, alpha=1 if large else 0.45,
                               ec=col, lw=1.6 if large else 0.6, ls="--" if large else "-"))
        pads = e["pads"]
        for px, py, num in pads:
            ax.add_patch(Circle((X(px), py), 0.18, fc="#555555", ec="none"))
        ones = [(px, py) for px, py, num in pads if str(num) == "1"]
        if ones and len({str(n) for _, _, n in pads}) > 1:
            ax.add_patch(Circle((X(ones[0][0]), ones[0][1]), 0.32, fc="red", ec="none"))
        lines = [e["ref"] + ("*" if e["hand"] else ""), short(e["value"])]
        if large:
            ax.text(x0 + 0.4, b["y1"] - 0.4, "  ".join(lines), ha="left", va="top", fontsize=1.3 * pt_per_mm,
                    fontweight="bold", color="black")
            continue
        vertical = bh > bw * 1.3
        along, across = (bh, bw) if vertical else (bw, bh)
        size = min(1.3, 0.42 * across, 0.95 * along / (0.62 * max(len(t) for t in lines)))
        ax.text((x0 + x1) / 2, (b["y0"] + b["y1"]) / 2, "\n".join(lines), ha="center", va="center",
                rotation=90 if vertical else 0, fontsize=max(3.5, size * pt_per_mm), linespacing=1.0,
                color="black", fontweight="bold")
    view = "BOTTOM side (seen from below, mirrored)" if mirror else "TOP side"
    fig.text(0.5, 0.965, f"{board} board: {view}", ha="center", fontsize=14, fontweight="bold")
    fig.text(0.5, 0.94, "red dot = pin 1;  * = hand-fitted part (not JLC-assembled);  same colour = same part, "
             "see the last page", ha="center", fontsize=8)
    pdf.savefig(fig)
    plt.close(fig)


def list_page(pdf, board, items, colours):
    rows = {}
    for e in items:
        key = (e["value"], e["footprint"])
        r = rows.setdefault(key, {"refs": [], "sides": set(), "mpn": e["mpn"], "lcsc": e["lcsc"]})
        r["refs"].append(e["ref"])
        r["sides"].add("top" if e["side"] == "front" else "bottom")
    fig = plt.figure(figsize=A4)
    fig.text(0.5, 0.965, f"{board} board: parts by value", ha="center", fontsize=14, fontweight="bold")
    y = 0.93
    step = min(0.028, 0.88 / max(len(rows), 1))
    for key, r in sorted(rows.items(), key=lambda kv: colours[kv[0]]):
        fig.patches.append(Rectangle((0.05, y - step * 0.35), 0.03, step * 0.7, transform=fig.transFigure,
                                     fc=colour(colours[key]), alpha=0.6, ec="black", lw=0.5))
        refs = ", ".join(sorted(r["refs"], key=ref_order))
        fig.text(0.10, y, f"{key[0]}  ({size_label(key[1])})", fontsize=8, fontweight="bold", va="center")
        fig.text(0.38, y, f"x{len(r['refs'])}  {'/'.join(sorted(r['sides']))}", fontsize=8, va="center")
        fig.text(0.50, y, refs, fontsize=7, va="center")
        fig.text(0.50, y - step * 0.42, f"{r['mpn']}  {r['lcsc']}".strip(), fontsize=5.5, va="center", color="#555555")
        y -= step
    pdf.savefig(fig)
    plt.close(fig)


def write(board, out=None):
    items = placements(board)
    colours = groups(items)
    out = Path(out) if out else build(board) / f"{board}_assembly.pdf"
    with PdfPages(out) as pdf:
        for side in ("front", "back"):
            on_side = [e for e in items if e["side"] == side]
            if on_side:
                side_page(pdf, board, side, on_side, colours)
        list_page(pdf, board, items, colours)
    return out


if __name__ == "__main__":
    print(write(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
