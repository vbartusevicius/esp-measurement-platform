"""Front-legend artwork as solid bodies, and the cover with the legend engraved.

    python3 mechanical/scripts/legend_engraving.py

Writes mechanical/build/<variant>/cover_embossed.step/.stl: the cover with the
legend artwork from front_legend.py (text outlines, LED rings) cut INLAY_DEPTH
deep into its faces, readable on a single-colour print. legend_bodies() / inlay()
/ led_ring() are reused by the wall-mount box and the 3D renders.
"""

from pathlib import Path

import build_enclosure as be
import cadquery as cq
import enclosure_features as ef
import front_legend as fl
from matplotlib.path import Path as MplPath

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "mechanical/build" / ef.VARIANT
INLAY_DEPTH = 0.3
TOLERANCE = 0.02
FACE_Z = {"front": ef.TOTAL_D, "top": ef.SHOULDER_Z["top"], "bottom": ef.SHOULDER_Z["bottom"]}


def rings(path):
    """Closed outlines of a matplotlib path; nesting depth decides outline or hole."""
    polygons = [p for p in path.to_polygons(closed_only=True) if len(p) > 3]
    nested = []
    for i, ring in enumerate(polygons):
        depth = sum(MplPath(other).contains_point(ring[0]) for j, other in enumerate(polygons) if j != i)
        nested.append((depth, [tuple(map(float, pt)) for pt in ring[:-1]]))
    return sorted(nested, key=lambda item: item[0])


def prism(points, z0, height):
    return cq.Workplane("XY", origin=(0, 0, z0)).polyline(points).close().extrude(height)


def inlay(path, face_z):
    """Solid of a filled path, from face_z - INLAY_DEPTH up to the face."""
    solid = None
    for depth, points in rings(path):
        body = prism(points, face_z - INLAY_DEPTH, INLAY_DEPTH)
        if depth % 2 == 0:
            solid = body if solid is None else solid.union(body)
        elif solid is not None:
            solid = solid.cut(body)
    return solid


def led_ring(window):
    outer = be.LED_WINDOW / 2 + fl.LED_RING
    inner = outer - fl.RING_LINE
    z0 = FACE_Z["front"] - INLAY_DEPTH
    return (cq.Workplane("XY", origin=(window["x"], window["y"], z0)).circle(outer).circle(inner)
            .extrude(INLAY_DEPTH))


def legend_bodies():
    bodies = []
    for label in fl.labels():
        bodies.append(inlay(label.path(), FACE_Z[fl.face_of(label.y)]))
    for mark in fl.marks():
        ext = mark.get_extents()
        bodies.append(inlay(mark, FACE_Z[fl.face_of((ext.y0 + ext.y1) / 2)]))
    bodies += [led_ring(w) for w in ef.led_windows()]
    legend = bodies[0]
    for body in bodies[1:]:
        legend = legend.union(body)
    return legend


def main():
    cover = be.build_cover().cut(legend_bodies())
    OUT.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(cover, str(OUT / "cover_embossed.step"), cq.exporters.ExportTypes.STEP)
    cq.exporters.export(cover, str(OUT / "cover_embossed.stl"), cq.exporters.ExportTypes.STL,
                        tolerance=TOLERANCE, angularTolerance=0.1)
    print(f"cover_embossed.stl/.step written to {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
