"""Render a board as realistic layer views with DRC markers (`eda` container).

    python3 hardware/scripts/render_board.py <board> <label>

Reads the stored layout (hardware/layout/<variant>/<board>/<board>.kicad_pcb),
runs KiCad DRC, and writes to hardware/build/<variant>/<board>/render/<label>/:
top, bottom (mirrored, as seen from below), in1, in2 and overlay, each as
.svg (opening at SVG_ZOOM x real size), plus drc.json and raster zoom_*.png
close-ups of the layout plan's zoom areas. Unrouted connections are red lines with red
rings at both ends; DRC violations are red rings, and every pad involved
in a violation or unrouted connection is filled red.
"""

import json
import subprocess
import sys
from pathlib import Path

import pcbnew
import yaml
from PIL import Image, ImageDraw, ImageFont

REPO = Path("/work")
sys.path.insert(0, str(REPO / "hardware/circuits"))
from product_spec import load_spec

SPEC = load_spec()
VARIANT = SPEC["active_variant"]
PX_PER_MM = 40
SVG_ZOOM = 2.25
MARGIN = 3.0
HEADER = 4.0

MASK = "#1d5c33"
MASK_COPPER = "#2f8a4a"
INNER_BG = "#0f1712"
INNER_COPPER = "#b87333"
PAD = "#d9b34a"
HOLE = "#0a0a0a"
SILK = "#f2f2f2"
ERROR = "#ff2a2a"
RATSNEST = "#e8d44d"
OK_TEXT = "#3ddc84"


def to_mm(v):
    return pcbnew.ToMM(v)


def outlines(polyset):
    shapes = []
    for i in range(polyset.OutlineCount()):
        rings = [polyset.Outline(i)] + [polyset.Hole(i, h) for h in range(polyset.HoleCount(i))]
        shapes.append([[(to_mm(r.CPoint(k).x), to_mm(r.CPoint(k).y))
                        for k in range(r.PointCount())] for r in rings])
    return shapes


def item_shapes(item, layer):
    polyset = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(polyset, layer, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
    return outlines(polyset)


class Canvas:
    def __init__(self, bounds, mirror, background):
        self.x0, self.y0, self.x1, self.y1 = bounds
        self.mirror = mirror
        self.w = self.x1 - self.x0 + 2 * MARGIN
        self.h = self.y1 - self.y0 + 2 * MARGIN + HEADER
        self.svg = []
        self.img = Image.new("RGB", (int(self.w * PX_PER_MM), int(self.h * PX_PER_MM)), background)
        self.draw = ImageDraw.Draw(self.img, "RGBA")
        self.background = background

    def pt(self, x, y):
        sx = (self.x1 - x) if self.mirror else (x - self.x0)
        return sx + MARGIN, y - self.y0 + MARGIN + HEADER

    def px(self, x, y):
        sx, sy = self.pt(x, y)
        return sx * PX_PER_MM, sy * PX_PER_MM

    def shape(self, rings, fill, opacity=1.0, hole_fill=None):
        path = " ".join("M " + " L ".join("{:.3f} {:.3f}".format(*self.pt(*p)) for p in ring) + " Z"
                        for ring in rings if len(ring) > 2)
        self.svg.append(f'<path d="{path}" fill="{fill}" fill-opacity="{opacity:.2f}" fill-rule="evenodd"/>')
        alpha = int(255 * opacity)
        if len(rings[0]) > 2:
            self.draw.polygon([self.px(*p) for p in rings[0]], fill=rgba(fill, alpha))
        for hole in rings[1:]:
            if len(hole) > 2:
                self.draw.polygon([self.px(*p) for p in hole], fill=rgba(hole_fill or self.background, 255))

    def circle(self, x, y, r, fill=None, stroke=None, width=0.15):
        cx, cy = self.pt(x, y)
        self.svg.append('<circle cx="{:.3f}" cy="{:.3f}" r="{:.3f}" fill="{}" stroke="{}" stroke-width="{:.3f}"/>'.format(cx, cy, r, fill or "none", stroke or "none", width))
        px, py = self.px(x, y)
        rp = r * PX_PER_MM
        self.draw.ellipse([px - rp, py - rp, px + rp, py + rp], fill=rgba(fill, 255) if fill else None,
                          outline=rgba(stroke, 255) if stroke else None,
                          width=max(1, int(width * PX_PER_MM)) if stroke else 0)

    def line(self, points, stroke, width):
        d = " L ".join("{:.3f} {:.3f}".format(*self.pt(*p)) for p in points)
        self.svg.append(f'<path d="M {d}" fill="none" stroke="{stroke}" stroke-width="{width:.3f}" stroke-linecap="round"/>')
        self.draw.line([self.px(*p) for p in points], fill=rgba(stroke, 255),
                       width=max(1, int(width * PX_PER_MM)))

    def text(self, x_mm, y_mm, s, fill, size, absolute=False):
        x, y = (x_mm, y_mm) if absolute else self.pt(x_mm, y_mm)
        self.svg.append(f'<text x="{x:.3f}" y="{y:.3f}" font-family="DejaVu Sans, sans-serif" '
                        f'font-size="{size:.2f}" fill="{fill}">{s}</text>')
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                                  max(8, int(size * PX_PER_MM)))
        self.draw.text((x * PX_PER_MM, (y - size) * PX_PER_MM), s, fill=rgba(fill, 255), font=font)

    def save(self, stem):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="{:.1f}mm" height="{:.1f}mm" '
               'viewBox="0 0 {:.3f} {:.3f}"><rect width="100%" height="100%" fill="{}"/>{}</svg>'.format(
                   self.w * SVG_ZOOM, self.h * SVG_ZOOM, self.w, self.h, self.background, "".join(self.svg)))
        stem.with_suffix(".svg").write_text(svg)


def rgba(color, alpha):
    c = color.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def run_drc(pcb_path, out):
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all",
                    "--output", str(out), str(pcb_path)], capture_output=True, check=False)
    return json.loads(out.read_text())


def drc_positions(drc):
    unrouted = [[(i["pos"]["x"], i["pos"]["y"]) for i in u["items"]]
                for u in drc.get("unconnected_items", [])]
    violations = [(v, [(i["pos"]["x"], i["pos"]["y"]) for i in v["items"]])
                  for v in drc.get("violations", []) if v["severity"] == "error"]
    return unrouted, violations


def flagged_pads(board, points):
    flagged = set()
    for fp in board.Footprints():
        for pad in fp.Pads():
            box = pad.GetBoundingBox()
            for x, y in points:
                if box.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))):
                    flagged.add(pad.m_Uuid.AsString())
    return flagged


def item_shapes_board_edges(board):
    polyset = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(polyset, False)
    return outlines(polyset)


def draw_copper(canvas, board, layer, color, opacity=1.0, hole_fill=None):
    for zone in board.Zones():
        if zone.GetIsRuleArea() or not zone.IsOnLayer(layer):
            continue
        for rings in outlines(zone.GetFilledPolysList(layer)):
            canvas.shape(rings, color, opacity, hole_fill)
    for track in board.GetTracks():
        if track.GetClass() != "PCB_VIA" and track.IsOnLayer(layer):
            for rings in item_shapes(track, layer):
                canvas.shape(rings, color, opacity)


def draw_vias(canvas, board, layer, color):
    for via in board.GetTracks():
        if via.GetClass() == "PCB_VIA" and via.IsOnLayer(layer):
            p = via.GetPosition()
            canvas.circle(to_mm(p.x), to_mm(p.y), to_mm(via.GetWidth(layer)) / 2, fill=color)
            canvas.circle(to_mm(p.x), to_mm(p.y), to_mm(via.GetDrillValue()) / 2, fill=HOLE)


def draw_pads(canvas, board, layer, flagged, color=PAD):
    for fp in board.Footprints():
        for pad in fp.Pads():
            if not pad.IsOnLayer(layer):
                continue
            fill = ERROR if pad.m_Uuid.AsString() in flagged else color
            for rings in item_shapes(pad, layer):
                canvas.shape(rings, fill)
            if pad.GetDrillSize().x > 0:
                p = pad.GetPosition()
                canvas.circle(to_mm(p.x), to_mm(p.y), to_mm(pad.GetDrillSize().x) / 2, fill=HOLE)


def draw_silk(canvas, board, layer):
    items = list(board.GetDrawings())
    for fp in board.Footprints():
        items += list(fp.GraphicalItems()) + [fp.Reference()]
    for item in items:
        if item.GetLayer() != layer or (hasattr(item, "IsVisible") and not item.IsVisible()):
            continue
        for rings in silk_shapes(item, layer):
            canvas.shape(rings, SILK)


def silk_shapes(item, layer):
    if not hasattr(item, "TransformTextToPolySet"):
        return item_shapes(item, layer)
    polyset = pcbnew.SHAPE_POLY_SET()
    item.TransformTextToPolySet(polyset, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
    return outlines(polyset)


def draw_courtyards(canvas, board, flipped, color, width=0.05):
    for fp in board.Footprints():
        if fp.IsFlipped() != flipped:
            continue
        fp.BuildCourtyardCaches()
        poly = fp.GetCourtyard(pcbnew.B_CrtYd if flipped else pcbnew.F_CrtYd)
        for rings in outlines(poly):
            canvas.line(rings[0] + rings[0][:1], color, width)
        p = fp.GetPosition()
        canvas.text(to_mm(p.x) - 0.6, to_mm(p.y) + 0.3, fp.GetReference(), color, 0.9)


def draw_errors(canvas, unrouted, violations, placement):
    for ends in unrouted:
        if placement:
            canvas.line(ends, RATSNEST, 0.08)
            continue
        canvas.line(ends, ERROR, 0.25)
        for x, y in ends:
            canvas.circle(x, y, 0.9, stroke=ERROR, width=0.25)
    for _, points in violations:
        for x, y in points:
            canvas.circle(x, y, 1.2, stroke=ERROR, width=0.3)


def header(canvas, name, view, drc):
    errors = sum(1 for v in drc.get("violations", []) if v["severity"] == "error")
    warnings = sum(1 for v in drc.get("violations", []) if v["severity"] == "warning")
    unrouted = len(drc.get("unconnected_items", []))
    ok = errors == 0 and unrouted == 0
    canvas.text(0.8, 2.2, f"{name} {view} | DRC errors {errors}, warnings {warnings} | unrouted {unrouted}",
                OK_TEXT if ok else ERROR, 1.6, absolute=True)


def bounds(board):
    box = board.GetBoardEdgesBoundingBox()
    return to_mm(box.GetLeft()), to_mm(box.GetTop()), to_mm(box.GetRight()), to_mm(box.GetBottom())


def save_zooms(canvases, zooms, out_dir):
    for name, z in zooms.items():
        for view, canvas in canvases.items():
            xs, ys = zip(canvas.px(z["x0"], -z["y0"]), canvas.px(z["x1"], -z["y1"]))
            crop = canvas.img.crop((int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))))
            crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
            crop.save(out_dir / f"zoom_{name}_{view}.png")


def render(name, label, placement):
    pcb_path = REPO / "hardware/layout" / VARIANT / name / f"{name}.kicad_pcb"
    out_dir = REPO / "hardware/build" / VARIANT / name / "render" / label
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = yaml.safe_load((REPO / "hardware/circuits/variants" / VARIANT
                           / f"layout_{name}.yaml").read_text())
    board = pcbnew.LoadBoard(str(pcb_path))
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    drc = run_drc(pcb_path, out_dir / "drc.json")
    unrouted, violations = drc_positions(drc)
    flagged = flagged_pads(board, [p for _, pts in violations for p in pts]
                           + ([] if placement else [p for ends in unrouted for p in ends]))
    canvases = {}
    outline = item_shapes_board_edges(board)
    box = bounds(board)

    for view, copper, silk, flipped in (("top", pcbnew.F_Cu, pcbnew.F_SilkS, False),
                                        ("bottom", pcbnew.B_Cu, pcbnew.B_SilkS, True)):
        canvas = Canvas(box, flipped, "#202020")
        for rings in outline:
            canvas.shape(rings, MASK, hole_fill="#202020")
        draw_copper(canvas, board, copper, MASK_COPPER, hole_fill=MASK)
        draw_vias(canvas, board, copper, MASK_COPPER)
        draw_pads(canvas, board, copper, flagged)
        draw_silk(canvas, board, silk)
        draw_errors(canvas, unrouted, violations, placement)
        header(canvas, name, view, drc)
        canvas.save(out_dir / view)
        canvases[view] = canvas

    for view, copper in (("in1", pcbnew.In1_Cu), ("in2", pcbnew.In2_Cu)):
        if not board.IsLayerEnabled(copper):
            continue
        canvas = Canvas(box, False, "#202020")
        for rings in outline:
            canvas.shape(rings, INNER_BG, hole_fill="#202020")
        draw_copper(canvas, board, copper, INNER_COPPER, hole_fill=INNER_BG)
        draw_vias(canvas, board, copper, INNER_COPPER)
        draw_pads(canvas, board, copper, flagged, INNER_COPPER)
        draw_errors(canvas, unrouted, violations, placement)
        header(canvas, name, view, drc)
        canvas.save(out_dir / view)
        canvases[view] = canvas

    canvas = Canvas(box, False, "#101010")
    for rings in outline:
        canvas.shape(rings, "#1a1a1a", hole_fill="#101010")
    for layer, color in ((pcbnew.B_Cu, "#3d7bff"), (pcbnew.In2_Cu, "#e8c547"), (pcbnew.F_Cu, "#ff5a3d")):
        if not board.IsLayerEnabled(layer):
            continue
        for track in board.GetTracks():
            if track.GetClass() != "PCB_VIA" and track.IsOnLayer(layer):
                for rings in item_shapes(track, layer):
                    canvas.shape(rings, color, 0.75)
        draw_pads(canvas, board, layer, flagged, color)
    draw_vias(canvas, board, pcbnew.F_Cu, "#cfcfcf")
    draw_courtyards(canvas, board, True, "#7fa8ff")
    draw_courtyards(canvas, board, False, "#ffb07f")
    draw_errors(canvas, unrouted, violations, placement)
    header(canvas, name, "overlay (front red, In2 yellow, back blue)", drc)
    canvas.save(out_dir / "overlay")
    canvases["overlay"] = canvas
    save_zooms(canvases, plan.get("zooms", {}), out_dir)

    errors = sum(1 for v in drc.get("violations", []) if v["severity"] == "error")
    print(f"{name}/{label}: DRC errors {errors}, unrouted {len(drc.get('unconnected_items', []))} "
          f"-> {out_dir.relative_to(REPO)}")
    warnings = {}
    for v in drc.get("violations", []):
        if v["severity"] == "error":
            print(f"  error {v['type']:<26} {' | '.join(i['description'] for i in v['items'])}")
        else:
            warnings[v["type"]] = warnings.get(v["type"], 0) + 1
    print("  warnings: " + ", ".join(f"{kind} {count}" for kind, count in sorted(warnings.items())))


if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2], "--placement" in sys.argv[3:])
