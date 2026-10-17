"""Fit drawing: case openings and supports over the real board parts.

Writes mechanical/build/<variant>/fit_front.svg and fit_side.svg.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import enclosure_features as ef
import matplotlib.pyplot as plt
import yaml
from matplotlib.patches import Circle, Rectangle

REPO = Path(__file__).resolve().parents[2]
SPEC = ef.SPEC
OUT = REPO / "mechanical/build" / ef.VARIANT
WALL = SPEC["enclosure"]["wall"]
UI_BOTTOM_Z = SPEC["front_ui"]["board_z"]
UI_THICK = SPEC["boards"]["ui"]["thickness"]
LABELLED = {"main": {"J1", "J2", "J3", "J4", "J5", "J6", "JP1", "U3", "U2", "U1", "L1", "F1", "D1", "D2"},
            "ui": {"SW1", "SW2", "D1", "D2", "D3", "J1", "J2"}}
COLOURS = {"main": "#2e7d32", "ui": "#1565c0"}
BOARDS = ef.SPEC["variants"][ef.VARIANT]["boards"]


def rect(ax, x, y, w, h, **kw):
    ax.add_patch(Rectangle((x, y), w, h, **kw))


def front_view():
    fig, ax = plt.subplots(figsize=(5, 10))
    half = ef.WIDTH / 2
    rect(ax, -half, 0, ef.WIDTH, ef.HIDDEN_H, fill=False, lw=2, ec="black")
    rect(ax, -half, ef.FRONT_Y_START, ef.WIDTH, ef.FRONT_H, fill=True, fc="#f2f2f2", ec="black", lw=1.5)
    boxes = ef.part_boxes()
    for board in BOARDS:
        colour = COLOURS[board]
        for slab in ef.board_slabs(board):
            rect(ax, slab["x0"], slab["y0"], slab["x1"] - slab["x0"], slab["y1"] - slab["y0"],
                 fill=False, ec=colour, ls="--", lw=1)
        comps = ef.components(board)
        for b in [p for p in boxes if p["board"] == board and p["ref"] in comps]:
            ref = b["ref"]
            x, y, bw, bh = b["x0"], b["y0"], b["x1"] - b["x0"], b["y1"] - b["y0"]
            if board == "main" and ef.FRONT_Y_START < y + bh / 2 < ef.FRONT_Y_END and ref not in LABELLED[board]:
                continue
            back = comps[ref]["side"] == "back"
            rect(ax, x, y, bw, bh, fill=False, ec=colour, lw=0.6, ls=":" if back else "-")
            if ref in LABELLED[board]:
                ax.text(x + bw / 2, y + bh / 2, f"{board}:{ref}", fontsize=6, ha="center",
                        va="center", color=colour)
    for h in ef.led_windows():
        rect(ax, h["x"] - 1.75, h["y"] - 1.75, 3.5, 3.5, fc="#ff7043", alpha=0.45, ec="#d84315")
    for h in ef.button_holes().values():
        ax.add_patch(Circle((h["x"], h["y"]), 1.75, fc="#ff7043", alpha=0.45, ec="#d84315"))
    win = ef.oled_window()
    rect(ax, win["cx"] - win["w"] / 2, win["cy"] - win["h"] / 2, win["w"], win["h"],
         fc="#ff7043", alpha=0.3, ec="#d84315")
    for s in ef.wire_entries():
        y_line = 0 if s.get("side") == "bottom" else ef.HIDDEN_H
        ax.plot([s["x0"], s["x1"]], [y_line, y_line], color="#ff7043", lw=5)
    ax.set_xlim(-half - 3, half + 3)
    ax.set_ylim(-3, ef.HIDDEN_H + 3)
    ax.set_aspect("equal")
    ax.set_title("Front view: openings (orange) over parts (green main, blue UI)", fontsize=8)
    ax.set_xlabel("x [mm]")
    ax.set_ylabel("y [mm]")
    ax.grid(alpha=0.2)
    return fig


def side_view():
    fig, ax = plt.subplots(figsize=(7, 10))
    lo, hi = ef.SHOULDER_Z["bottom"], ef.SHOULDER_Z["top"]
    profile = [(0, 0), (lo, 0), (lo, ef.FRONT_Y_START), (ef.TOTAL_D, ef.FRONT_Y_START),
               (ef.TOTAL_D, ef.FRONT_Y_END), (hi, ef.FRONT_Y_END), (hi, ef.HIDDEN_H),
               (0, ef.HIDDEN_H), (0, 0)]
    ax.plot(*zip(*profile), color="black", lw=2)
    inner = [(WALL, WALL), (lo - WALL, WALL), (lo - WALL, ef.FRONT_Y_START + WALL),
             (ef.TOTAL_D - WALL, ef.FRONT_Y_START + WALL), (ef.TOTAL_D - WALL, ef.FRONT_Y_END - WALL),
             (hi - WALL, ef.FRONT_Y_END - WALL), (hi - WALL, ef.HIDDEN_H - WALL),
             (WALL, ef.HIDDEN_H - WALL), (WALL, WALL)]
    ax.plot(*zip(*inner), color="black", lw=0.8, ls=":")
    for board in BOARDS:
        colour = COLOURS[board]
        for slab in ef.board_slabs(board):
            rect(ax, slab["z0"], slab["y0"], slab["z1"] - slab["z0"], slab["y1"] - slab["y0"],
                 fc=colour, alpha=0.85, ec=colour)
    for b in ef.part_boxes():
        board, ref = b["board"], b["ref"]
        colour = COLOURS[board]
        rect(ax, b["z0"], b["y0"], b["z1"] - b["z0"], b["y1"] - b["y0"],
             fc=colour, alpha=0.18, ec=colour, lw=0.5)
        if ref in LABELLED.get(board, set()) or "OLED" in ref:
            ax.text((b["z0"] + b["z1"]) / 2, (b["y0"] + b["y1"]) / 2,
                    ref if board == "main" else f"{board}:{ref}", fontsize=6, ha="center", va="center")
    ax.set_xlim(-2, ef.TOTAL_D + 5)
    ax.set_ylim(-3, ef.HIDDEN_H + 3)
    ax.set_aspect("equal")
    ax.set_title("Side section (z from rail -> front): boards & component envelopes", fontsize=8)
    ax.set_xlabel("z from rail face [mm]")
    ax.set_ylabel("y [mm]")
    ax.grid(alpha=0.2)
    return fig


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in (("fit_front", front_view), ("fit_side", side_view)):
        fig = fn()
        fig.savefig(OUT / f"{name}.svg", bbox_inches="tight")
        plt.close(fig)
    print(f"fit_front.svg and fit_side.svg written to {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
