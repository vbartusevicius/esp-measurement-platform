"""Legend artwork as solid bodies: inlay() turns a front_legend path into a prism
INLAY_DEPTH deep, which the base (side_legend_cuts), the wall-mount box and the
3D renders cut or show. The front carries no text any more (button pad marks
instead), so there is no separate engraved cover.
"""

import cadquery as cq
import enclosure_features as ef
import front_legend as fl
from matplotlib.path import Path as MplPath

INLAY_DEPTH = 0.6   # powder prints smear shallower legends
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


def legend_bodies():
    """Front legend solids (front_legend.labels / marks), or None: the front carries none now."""
    bodies = [inlay(label.path(), FACE_Z[fl.face_of(label.y)]) for label in fl.labels()]
    for mark in fl.marks():
        ext = mark.get_extents()
        bodies.append(inlay(mark, FACE_Z[fl.face_of((ext.y0 + ext.y1) / 2)]))
    if not bodies:
        return None
    legend = bodies[0]
    for body in bodies[1:]:
        legend = legend.union(body)
    return legend
