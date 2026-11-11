"""Legend layout for the 1-DIN case: labels as outlined text paths with their
faces, openings and keep-outs. The front carries no text (button pad marks
instead); side_labels() are the connector names engraved into the base's side
(build_enclosure.side_legend_cuts) and the wall box's lid."""

from dataclasses import dataclass

import build_enclosure as be
import enclosure_features as ef
from matplotlib.path import Path as MplPath
from matplotlib.textpath import TextPath
from matplotlib.transforms import Affine2D

# Smallest legend a powder print (MJF / SLS) keeps legible when recessed
# legend_engraving.INLAY_DEPTH deep: 3 mm text, whose DejaVu Sans Bold strokes are ~0.5 mm.
MIN_TEXT_H = 3.0
MIN_STROKE = 0.4
LABEL_H = 3.0
EDGE = 1.0
LABEL_SPACING = 0.3
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
    """No text on the front: the buttons are told apart by their pad marks (a plain
    dot for page / acknowledge, an X for reset / WiFi, build_enclosure.BUTTON_MARK),
    the LEDs carry neither words nor rings, and the connector names are engraved
    beside the connectors (side_labels)."""
    return []


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
