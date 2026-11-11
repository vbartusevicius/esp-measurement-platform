"""Assembly drawings for hand soldering: where each part goes and which way round,
even where the silkscreen reference had to be hidden.

    python3 hardware/scripts/assembly_drawing.py <board> [out.pdf]

Writes a PDF (default hardware/build/<variant>/<board>/<board>_assembly.pdf):
- one page per populated side (the bottom mirrored, as seen from below): every
  part's body at its place with its reference (the value is its colour; large
  parts also show the value on a white tag),
  parts of the same value in the same colour, large parts dashed and drawn
  under the small ones, a black corner flag on hand-fitted parts;
- polarity only where orientation matters, the way the real part is marked
  (polarity()): a black cathode bar on diodes, a red + on polarised
  capacitors, a red dot with "1" on pin 1 of ICs, transistors, LEDs,
  connectors and modules; nothing on resistors, ceramic capacitors, inductors,
  fuses, crystals, pin strips and push buttons;
- a values page (value, size, quantity, side, references) and a key page.
Reads only components_<board>.json, parts.json and the layout plan's outline.
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
BIG_MM2 = 60.0        # bodies larger than this (modules, terminals, relay) are dashed outlines, drawn first
MIN_REF_PT = 6.0      # readable at 100 % on A4
REF_MAX_PT = 9.0
NON_POLAR = ("R_", "C_", "L_", "Fuse_", "Crystal_", "PinHeader", "PinSocket", "SW_")


def build(board):
    return REPO / "hardware/build" / VARIANT / board


def outline(board):
    frame = yaml.safe_load((REPO / "hardware/circuits/variants" / VARIANT / f"layout_{board}.yaml").read_text())["frame"]
    if frame.get("outline"):
        return [tuple(p) for p in frame["outline"]]
    w, h = frame["size"]["x"], frame["size"]["y"]
    return [(0, 0), (w, 0), (w, h), (0, h)]


def polarity(footprint, value):
    """'cathode' (bar at pad 1: KiCad diode footprints put K on pad 1), 'plus'
    (pad 1 of CP_ footprints), 'pin1' or None where orientation does not matter.
    Bidirectional TVS diodes (values ending in CA, e.g. SMAJ40CA) are non-polar."""
    name = footprint.split(":")[-1]
    if name.startswith(("D_SMA", "D_SMB", "D_SMC", "D_SOD", "D_MiniMELF", "D_DO")):
        return None if value.upper().endswith("CA") else "cathode"
    if name.startswith("CP_"):
        return "plus"
    if name.startswith(NON_POLAR):
        return None
    return "pin1"


def placements(board):
    """One entry per part: ref, value, part number, side, body box, pads, polarity mark."""
    comps = {c["ref"]: c for c in json.loads((build(board) / f"components_{board}.json").read_text())}
    parts = {p["ref"]: p for p in json.loads((build(board) / "parts.json").read_text())}
    out = []
    for ref, c in comps.items():
        p = parts.get(ref, {})
        out.append({"ref": ref, "value": c["value"], "mpn": p.get("mpn", ""), "lcsc": p.get("lcsc", ""),
                    "hand": p.get("assembly") == "hand", "side": c["side"], "bbox": c["bbox"],
                    "footprint": c["footprint"], "pads": c["pads"], "mark": polarity(c["footprint"], c["value"])})
    return sorted(out, key=lambda e: (e["side"], e["value"], e["ref"]))


def pad_one(e):
    """Centre of pad 1 (the mean of all its copper, for split pads)."""
    pts = [(x, y) for x, y, n in e["pads"] if str(n) == "1"]
    if not pts:
        return None
    return sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)


def groups(items):
    keys = sorted({(e["value"], e["footprint"]) for e in items})
    return {k: i for i, k in enumerate(keys)}


def colour(i):
    return plt.get_cmap("tab20")(i % 20)


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
    for token in ("0402", "0603", "0805", "1206", "1210", "1812", "TSOT-23-6", "SOT-23-6", "SOT-23-5", "SOT-23",
                  "SMA", "SOD-123"):
        if token in footprint:
            return token
    return footprint.split("_")[0] if "_" in footprint else footprint


def draw_mark(ax, e, X, size_mm):
    b = e["bbox"]
    one = pad_one(e)
    if e["mark"] is None or one is None:
        return
    px, py = X(one[0]), one[1]
    if e["mark"] == "pin1":
        r = max(0.45, min(0.65, size_mm * 0.35))
        ax.add_patch(Circle((px, py), r, fc="red", ec="white", lw=0.4, zorder=6))
        ax.text(px, py, "1", ha="center", va="center", fontsize=r * 1.5 * PT[0], color="white",
                fontweight="bold", zorder=7)
        return
    if e["mark"] == "plus":
        ax.text(px, py, "+", ha="center", va="center", fontsize=1.8 * PT[0], color="red", fontweight="bold", zorder=7)
        return
    # cathode bar across the body at the pad-1 end, like the band on the part
    x0, x1 = sorted((X(b["x0"]), X(b["x1"])))
    cx, cy = (x0 + x1) / 2, (b["y0"] + b["y1"]) / 2
    if abs(px - cx) >= abs(py - cy):
        w = 0.18 * (x1 - x0)
        bx = x1 - w if px > cx else x0
        ax.add_patch(Rectangle((bx, b["y0"]), w, b["y1"] - b["y0"], fc="black", ec="none", zorder=6))
    else:
        h = 0.18 * (b["y1"] - b["y0"])
        by = b["y1"] - h if py > cy else b["y0"]
        ax.add_patch(Rectangle((x0, by), x1 - x0, h, fc="black", ec="none", zorder=6))


PT = [1.0]   # points per board millimetre on the current page


def side_page(pdf, board, side, items, colours):
    shape = outline(board)
    xs, ys = [p[0] for p in shape], [p[1] for p in shape]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    mirror = side == "back"

    def X(x):
        return (max(xs) - x + min(xs)) if mirror else x

    fig = plt.figure(figsize=A4)
    ax = fig.add_axes((0.04, 0.04, 0.92, 0.88))
    ax.set_aspect("equal")
    ax.axis("off")
    pad = 1.5
    ax.set_xlim(min(xs) - pad, max(xs) + pad)
    ax.set_ylim(min(ys) - pad, max(ys) + pad)
    frame = ax.get_position()
    mm_per_inch = max((w + 2 * pad) / (A4[0] * frame.width), (h + 2 * pad) / (A4[1] * frame.height))
    PT[0] = 72 / mm_per_inch
    ax.add_patch(Polygon([(X(x), y) for x, y in shape], closed=True, fc="white", ec="black", lw=1.2))
    big = sorted([e for e in items if area(e) > BIG_MM2], key=area, reverse=True)
    for e in big + [e for e in items if area(e) <= BIG_MM2]:
        b = e["bbox"]
        x0, x1 = sorted((X(b["x0"]), X(b["x1"])))
        bw, bh = x1 - x0, b["y1"] - b["y0"]
        col = colour(colours[(e["value"], e["footprint"])])
        large = area(e) > BIG_MM2
        ax.add_patch(Rectangle((x0, b["y0"]), bw, bh, fc="none" if large else col, alpha=1 if large else 0.45,
                               ec=col, lw=1.8 if large else 0.6, ls="--" if large else "-", zorder=2 if large else 3))
        if e["hand"]:
            f = min(1.6, 0.35 * min(bw, bh))
            # top-right corner: the top-left one carries the large parts' label tag
            ax.add_patch(Polygon([(x1, b["y1"]), (x1 - f, b["y1"]), (x1, b["y1"] - f)], closed=True, fc="black",
                                 zorder=9))
        ref = e["ref"]
        if large:
            ax.text(x0 + 0.4, b["y1"] - 0.4, f"{ref}\n{short(e['value'])}", ha="left", va="top", linespacing=1.1,
                    fontsize=MIN_REF_PT + 1, zorder=8,
                    bbox={"fc": "white", "ec": col, "lw": 0.6, "pad": 1.2})
            draw_mark(ax, e, X, 1.2)
            continue
        # the reference only: the value is the part's colour (values page); text never bold or stacked
        vertical = bh > bw * 1.3
        tx, ty = (x0 + x1) / 2, (b["y0"] + b["y1"]) / 2
        if e["mark"] == "cathode" and pad_one(e):
            one_x, one_y = X(pad_one(e)[0]), pad_one(e)[1]
            if abs(one_x - tx) >= abs(one_y - ty):
                tx += -0.09 * bw if one_x > tx else 0.09 * bw
                bw *= 0.82
            else:
                ty += -0.09 * bh if one_y > ty else 0.09 * bh
                bh *= 0.82
        along, across = (bh, bw) if vertical else (bw, bh)
        fit_pt = min(across * 0.7, along * 0.85 / (0.6 * max(len(ref), 2))) * PT[0]
        ax.text(tx, ty, ref, ha="center", va="center", rotation=90 if vertical else 0,
                fontsize=min(REF_MAX_PT, max(MIN_REF_PT, fit_pt)), color="black", zorder=8)
        draw_mark(ax, e, X, min(x1 - x0, b["y1"] - b["y0"]))
    view = "BOTTOM side (seen from below, mirrored)" if mirror else "TOP side"
    fig.text(0.5, 0.965, f"{board} board: {view}", ha="center", fontsize=14, fontweight="bold")
    fig.text(0.5, 0.94, "black bar = diode cathode;  red + = capacitor +;  red 1 = pin 1;  black corner = hand-fitted;"
             "  same colour = same value (values page)", ha="center", fontsize=8)
    pdf.savefig(fig)
    plt.close(fig)


def list_page(pdf, board, items, colours):
    rows = {}
    for e in items:
        key = (e["value"], e["footprint"])
        r = rows.setdefault(key, {"refs": [], "sides": set(), "mpn": e["mpn"], "lcsc": e["lcsc"], "mark": e["mark"]})
        r["refs"].append(e["ref"])
        r["sides"].add("top" if e["side"] == "front" else "bottom")
    fig = plt.figure(figsize=A4)
    fig.text(0.5, 0.965, f"{board} board: parts by value", ha="center", fontsize=14, fontweight="bold")
    marks = {"cathode": "cathode bar", "plus": "+ pad", "pin1": "pin 1", None: "-"}
    y = 0.93
    step = min(0.03, 0.88 / max(len(rows), 1))
    for key, r in sorted(rows.items(), key=lambda kv: colours[kv[0]]):
        fig.patches.append(Rectangle((0.04, y - step * 0.35), 0.03, step * 0.7, transform=fig.transFigure,
                                     fc=colour(colours[key]), alpha=0.6, ec="black", lw=0.5))
        fig.text(0.09, y, f"{short(key[0])}  ({size_label(key[1])})", fontsize=9, fontweight="bold", va="center")
        fig.text(0.37, y, f"x{len(r['refs'])}  {'/'.join(sorted(r['sides']))}", fontsize=9, va="center")
        fig.text(0.49, y, marks[r["mark"]], fontsize=8, va="center", color="#aa0000")
        fig.text(0.60, y, ", ".join(sorted(r["refs"], key=ref_order)), fontsize=8, va="center")
        fig.text(0.60, y - step * 0.4, f"{r['mpn']}  {r['lcsc']}".strip(), fontsize=6, va="center", color="#555555")
        y -= step
    pdf.savefig(fig)
    plt.close(fig)


KEY = [
    ("Marks on the drawing", True),
    ("Black bar across a diode: the cathode end. Put the band printed on the diode on this side.", False),
    ("Red +: the + pad of an electrolytic or tantalum capacitor.", False),
    ("Red dot with 1: pin 1 of an IC, transistor, LED, connector or module.", False),
    ("No mark: resistors, ceramic capacitors, inductors, fuses, crystals, pin strips and push buttons can go "
     "either way round. Bidirectional TVS diodes (part numbers ending in CA) have no polarity either.", False),
    ("Black top-right corner: hand-fitted part (not placed by JLCPCB), e.g. a socketed module or a terminal JLC has no stock of.", False),
    ("The bottom page is mirrored: it shows the board as you see it after flipping it over.", False),
    ("", False),
    ("Finding pin 1 on the real part", True),
    ("SOT-23 (3 legs): the single leg on its own side is pin 3; pins 1 and 2 are on the opposite side.", False),
    ("SOT-23-5 / TSOT-23-6 / SC-70 / SO / QFN: a dot or a bevelled edge on the body marks pin 1.", False),
    ("Addressable RGB LEDs: one corner of the body or lens is marked (a cut corner or a dot). Which pin it marks "
     "differs between makers: check the part's datasheet before soldering, it is easy to misread.", False),
    ("0805 LEDs: pin 1 is the cathode, usually a green line or a T on the underside.", False),
    ("Diodes: the band is the cathode.", False),
    ("Electrolytic capacitors: the stripe on the can marks the - side; the + pad is the other one.", False),
    ("Modules and connectors: match the pin-1 dot to the module's pin-1 marking or to the drawing in its "
     "datasheet; for modules on sockets, check the outline (e.g. USB connector towards the board edge).", False),
    ("", False),
    ("Tools", True),
    ("0805 parts and SOT-23: a 3-5x magnifier lamp or a 10x loupe to read markings and check joints.", False),
    ("SC-70, QFN and fine-pitch connectors: a USB microscope helps to see bridges and pin-1 marks.", False),
    ("Flux, fine solder (0.5 mm) and a chisel or fine conical tip; tweezers for placing.", False),
]


def key_page(pdf, board):
    fig = plt.figure(figsize=A4)
    fig.text(0.5, 0.965, f"{board} board: key", ha="center", fontsize=14, fontweight="bold")
    y = 0.92
    for text, heading in KEY:
        if heading:
            fig.text(0.07, y, text, fontsize=12, fontweight="bold", va="top")
            y -= 0.03
            continue
        lines = _wrap(text, 95)
        for line in lines:
            fig.text(0.09, y, line, fontsize=10, va="top")
            y -= 0.022
        y -= 0.006
    pdf.savefig(fig)
    plt.close(fig)


def _wrap(text, width):
    words, lines, line = text.split(), [], ""
    for word in words:
        if len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + ([line] if line else []) or [""]


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
        key_page(pdf, board)
    return out


if __name__ == "__main__":
    print(write(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
