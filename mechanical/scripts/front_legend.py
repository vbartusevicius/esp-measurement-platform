"""Front legend artwork for the 1-DIN Universal Sensor Node cover.

Writes mechanical/build/<variant>/front_legend.svg/.pdf (1:1).
"""

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import build_enclosure as be
import enclosure_features as ef
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, PathPatch, Rectangle
from matplotlib.path import Path as MplPath
from matplotlib.textpath import TextPath
from matplotlib.transforms import Affine2D

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "mechanical/build" / ef.VARIANT
EDGE = 1.0
LABEL_SPACING = 0.3
INK = "#000000"
GUIDE = "#00acc1"
LED_RING = 0.25
RING_LINE = 0.25
FONT = {"family": "DejaVu Sans", "weight": "bold"}
LINE_SPACING = 1.3
SIGN_REFERENCE = "+"


@dataclass
class Label:
    text: str
    x: float
    y: float
    height: float

    def path(self):
        lines = self.text.split("\n")
        parts = []
        for i, line in enumerate(lines):
            raw = TextPath((0, 0), line, size=self.height, prop=FONT)
            ext = raw.get_extents()
            vertical = TextPath((0, 0), SIGN_REFERENCE, size=self.height, prop=FONT).get_extents() \
                if len(line) == 1 else ext
            dy = (len(lines) - 1) / 2 * self.height * LINE_SPACING - i * self.height * LINE_SPACING
            parts.append(raw.transformed(Affine2D().translate(self.x - ext.x0 - ext.width / 2,
                                                              self.y + dy - vertical.y0 - vertical.height / 2)))
        return MplPath.make_compound_path(*parts)

    def box(self):
        ext = self.path().get_extents()
        return ext.x0, ext.y0, ext.x1, ext.y1


def faces():
    half = ef.WIDTH / 2
    return {"bottom": (-half, 0.0, half, ef.FRONT_Y_START),
            "front": (-half, ef.FRONT_Y_START, half, ef.FRONT_Y_END),
            "top": (-half, ef.FRONT_Y_END, half, ef.HIDDEN_H)}


def openings():
    items = []
    for h in ef.button_holes().values():
        r = be.BUTTON_HOLE / 2
        items.append(("circle", h["x"] - r, h["y"] - r, h["x"] + r, h["y"] + r))
    for h in ef.led_windows():
        r = be.LED_WINDOW / 2 + LED_RING
        items.append(("led", h["x"] - r, h["y"] - r, h["x"] + r, h["y"] + r))
    win = ef.oled_window()
    items.append(("rect", win["cx"] - win["w"] / 2, win["cy"] - win["h"] / 2,
                  win["cx"] + win["w"] / 2, win["cy"] + win["h"] / 2))
    return items


def overlaps(a, b, margin=0.0):
    return a[0] < b[2] + margin and b[0] < a[2] + margin and a[1] < b[3] + margin and b[1] < a[3] + margin


def inside(box, face, margin=EDGE):
    return face[0] + margin <= box[0] and box[2] <= face[2] - margin and \
        face[1] + margin <= box[1] and box[3] <= face[3] - margin


def face_of(y):
    return next(name for name, f in faces().items() if f[1] <= y <= f[3])


def marks():
    return []


def labels():
    return [
        # Top & bottom shoulders: clean section titles only (pin numbers & legend
        # are embossed on the side wall directly aligned with each J1/J2 pole)
        Label("J2 SENSOR", 0.0, 71.0, 1.8),
        Label("J1 PWR/RLY", 0.0, 8.5, 1.7),

        # Front protrusion: buttons & status LEDs
        Label("RST/WIFI", -4.1, 28.6, 1.15),
        Label("PAGE", 4.1, 28.6, 1.15),
        Label("STATUS", -4.8, 19.6, 0.85),
        Label("NET", 0.0, 19.6, 0.85),
        Label("SENS", 4.8, 19.6, 0.85),
    ]


def draw(ax, placed):
    for name, (x0, y0, x1, y1) in faces().items():
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=GUIDE, lw=0.3, gid=f"guides-face-{name}"))
    for kind, x0, y0, x1, y1 in openings():
        if kind == "rect":
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=GUIDE, lw=0.3, gid="guides-opening"))
        else:
            r = be.LED_WINDOW / 2 if kind == "led" else (x1 - x0) / 2
            ax.add_patch(Circle(((x0 + x1) / 2, (y0 + y1) / 2), r, fill=False, ec=GUIDE, lw=0.3,
                                gid="guides-opening"))
    for window in ef.led_windows():
        ax.add_patch(Circle((window["x"], window["y"]), be.LED_WINDOW / 2 + LED_RING - RING_LINE / 2, fill=False,
                            ec=INK, lw=RING_LINE * 72 / 25.4, gid="print-led-ring"))
    for label in placed:
        ax.add_patch(PathPatch(label.path(), fc=INK, ec="none", gid="print-text"))
    for mark in marks():
        ax.add_patch(PathPatch(mark, fc=INK, ec="none", gid="print-bracket"))


def render(placed):
    margin = 6.0
    width, height = ef.WIDTH + 2 * margin, ef.HIDDEN_H + 2 * margin + 8
    fig = plt.figure(figsize=(width / 25.4, height / 25.4))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(-ef.WIDTH / 2 - margin, ef.WIDTH / 2 + margin)
    ax.set_ylim(-margin, ef.HIDDEN_H + margin + 8)
    ax.set_aspect("equal")
    ax.axis("off")
    draw(ax, placed)
    ax.plot([-ef.WIDTH / 2, -ef.WIDTH / 2 + 10], [-margin / 2] * 2, color=GUIDE, lw=0.5, gid="guides-scale")
    ax.text(-ef.WIDTH / 2 + 11, -margin / 2, "10 mm (1:1); cyan = guides, not printed", fontsize=4,
            va="center", color=GUIDE, gid="guides-note")
    ax.text(0, ef.HIDDEN_H + margin / 2 + 4, f"ESP Measurement Platform {ef.VARIANT} front legend, front view",
            fontsize=5, ha="center", color=GUIDE, gid="guides-title")
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams["svg.fonttype"] = "path"
    for suffix in ("svg", "pdf"):
        fig.savefig(OUT / f"front_legend.{suffix}")
    plt.close(fig)


def main():
    render(labels())
    print(f"front_legend written to {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
