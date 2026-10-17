"""Full-colour cover for WJP (White Jet Process) resin printing, e.g. JLC3DP
"Full-Color Resin".

    python3 mechanical/scripts/legend_color_model.py

Writes mechanical/build/<variant>/cover_color.3mf and cover_color_obj.zip
(OBJ + MTL, one material per colour). The legend artwork from front_legend.py
(text outlines, LED rings, the DALI bracket) is inlaid flush into the cover's
faces as separate black bodies INLAY_DEPTH deep; the cover is cut by exactly
the same bodies, so colour and cover share faces without gaps or overlaps, as
JLC3DP asks for separately coloured regions.
"""

import io
import zipfile
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
COLOURS = {"cover": (0.95, 0.95, 0.95), "legend": (0.05, 0.05, 0.05)}
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


def mesh(shape):
    vertices, triangles = shape.val().tessellate(TOLERANCE, 0.2)
    return [(v.x, v.y, v.z) for v in vertices], triangles


def write_3mf(parts, path):
    materials = "".join(f'<base name="{name}" displaycolor="#{"".join(f"{round(c * 255):02X}" for c in rgb)}"/>'
                        for name, rgb in COLOURS.items())
    objects, items = [], []
    for index, (name, (vertices, triangles)) in enumerate(parts.items(), start=2):
        v = "".join(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in vertices)
        t = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in triangles)
        objects.append(f'<object id="{index}" name="{name}" type="model" pid="1" pindex="{list(COLOURS).index(name)}">'
                       f'<mesh><vertices>{v}</vertices><triangles>{t}</triangles></mesh></object>')
        items.append(f'<item objectid="{index}"/>')
    model = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             f'<resources><basematerials id="1">{materials}</basematerials>{"".join(objects)}</resources>'
             f'<build>{"".join(items)}</build></model>')
    types = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("3D/3dmodel.model", model)


def write_obj_zip(parts, path):
    obj, mtl = io.StringIO(), io.StringIO()
    obj.write("mtllib cover_color.mtl\n")
    offset = 1
    for name, (vertices, triangles) in parts.items():
        mtl.write(f"newmtl {name}\nKd {' '.join(f'{c:.3f}' for c in COLOURS[name])}\nKa 0 0 0\nKs 0 0 0\nd 1\nillum 1\n\n")
        obj.write(f"o {name}\nusemtl {name}\n")
        obj.writelines(f"v {x:.4f} {y:.4f} {z:.4f}\n" for x, y, z in vertices)
        obj.writelines(f"f {a + offset} {b + offset} {c + offset}\n" for a, b, c in triangles)
        offset += len(vertices)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("cover_color.obj", obj.getvalue())
        archive.writestr("cover_color.mtl", mtl.getvalue())


def main():
    legend = legend_bodies()
    cover = be.build_cover().cut(legend)
    parts = {"cover": mesh(cover), "legend": mesh(legend)}
    OUT.mkdir(parents=True, exist_ok=True)
    write_3mf(parts, OUT / "cover_color.3mf")
    write_obj_zip(parts, OUT / "cover_color_obj.zip")
    cq.exporters.export(cover, str(OUT / "cover_embossed.step"), cq.exporters.ExportTypes.STEP)
    cq.exporters.export(cover, str(OUT / "cover_embossed.stl"), cq.exporters.ExportTypes.STL,
                        tolerance=TOLERANCE, angularTolerance=0.1)
    print(f"cover_color.3mf + cover_color_obj.zip + cover_embossed.stl/.step written to {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
