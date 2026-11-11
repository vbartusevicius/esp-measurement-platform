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
# Smallest legend a powder print (MJF / SLS) keeps legible when recessed
# legend_engraving.INLAY_DEPTH deep: 3 mm text, whose DejaVu Sans Bold strokes are ~0.5 mm.
MIN_TEXT_H = 3.0
MIN_STROKE = 0.4
LABEL_H = 3.0
EDGE = 1.0
LABEL_SPACING = 0.3
INK = "#000000"
GUIDE = "#00acc1"
LED_RING = 0.6   # keep-out around each LED window (no ring is engraved)
FONT = {"family": "DejaVu Sans", "weight": "bold"}
LINE_SPACING = 1.3
SIGN_REFERENCE = "+"


@dataclass
class Label:
    text: str
    x: float
    y: float
    height: float
    angle: float = 0.0   # 90 = reading upwards

    def path(self):
        flat = self.flat_path()
        if not self.angle:
            return flat
        return flat.transformed(Affine2D().rotate_deg_around(self.x, self.y, self.angle))

    def flat_path(self):
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
        (cx, cy, d), (x0, x1, y0, y1) = be.button_tab_outline(h, be.BUTTON_TAB["slot"])
        items.append(("circle", cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2))
        items.append(("rect", x0, y0, x1, y1))
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
    """Front: short button names only (3 mm text does not fit "RST/WIFI" or
    "PAGE" on the 18 mm face); the LEDs carry rings, not words, and the
    connector names are engraved beside the connectors (side_labels). The
    release README explains RST, PG and the LED order."""
    holes = ef.button_holes()
    # Temporarily on the bottom shoulder, under their buttons: the front strip has no
    # room above the lying buttons now (button markings to be decided)
    y = ef.FRONT_Y_START - EDGE - LABEL_H / 2 - 0.5
    return [Label("RST", holes["RESET"]["x"], y, LABEL_H), Label("PG", holes["PROG"]["x"], y, LABEL_H)]


SIDE_GAP = 0.6   # between side labels and windows / keepers / each other


def side_keepouts():
    """(u0, v0, u1, v1) of what lies under or in the right side face: the snap
    keepers cut into the wall from inside and the J4 screwdriver holes."""
    import build_enclosure as be_
    boxes = []
    for k in be_.shoulder_snap_keepers():
        bb = k.val().BoundingBox()
        if bb.xmax > be_.INNER_W / 2:
            boxes.append((-bb.zmax, bb.ymin, -bb.zmin, bb.ymax))
    boxes += [(-h["z"] - h["d"] / 2, h["y"] - h["d"] / 2, -h["z"] + h["d"] / 2, h["y"] + h["d"] / 2)
              for h in be_.screw_holes()]
    return boxes


def side_to_enc(u, v):
    """Right side face (x = WIDTH / 2), seen from the right with the device
    upright: u runs from the front towards the rail (-z), v up (+y)."""
    return -u, v


def side_labels():
    """Engraved into the base's right side face beside the terminals, 3 mm:
    each sensor-bank pole's signal name reading upwards beside it (pole
    numbers 1..10 would not pass the stroke check at the 3.5 mm pitch; the
    README numbers them), and J1 (supply) and J4 (relay) pole names in one row
    just above J4's screwdriver holes, each block titled with its rating. Label
    coordinates are (u, v) = (-z, y)."""
    import build_enclosure as be_
    out = []
    names = ("5V", "24V", "mA", "10V", "IO1", "IO2", "IO3", "IO4", "GND", "GND")
    zs = be_.sensor_pole_z()
    top = ef.HIDDEN_H - be_.WALL - LABEL_H / 2 - 0.4
    for z, name in zip(zs, names):
        probe = Label(name, -z, 0.0, LABEL_H, 90.0)
        length = probe.box()[3] - probe.box()[1]
        out.append(Label(name, -z, top + LABEL_H / 2 - length / 2, LABEL_H, 90.0))
    window_top = max(h["y"] + h["d"] / 2 for h in be_.screw_holes()) + SIDE_GAP
    names_by_ref = {"J1": {"1": "GND", "2": "VIN"},
                    "J4": dict(zip(("1", "2", "3"), ef.SPEC["terminals"]["relay_out"]["labels"]))}
    titles = {"J1": "9-30V", "J4": "230V"}
    for ref, by_pin in names_by_ref.items():
        pins = be_._pin_z_positions(ref)
        tops = []
        for pin, z in pins.items():
            probe = Label(by_pin[pin], -z, 0.0, LABEL_H, 90.0)
            length = probe.box()[3] - probe.box()[1]
            out.append(Label(by_pin[pin], -z, window_top + length / 2, LABEL_H, 90.0))
            tops.append(window_top + length)
        centre = -sum(pins.values()) / len(pins)
        title = Label(titles[ref], centre, max(tops) + SIDE_GAP + LABEL_H / 2, LABEL_H)
        while any(overlaps(title.box(), k, SIDE_GAP) for k in side_keepouts()):
            title.y += 0.25
        out.append(title)
    return out


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
