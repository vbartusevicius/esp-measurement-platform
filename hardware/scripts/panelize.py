"""Build a single breakaway mouse-bite PCB panel combining all boards of a variant.

Generates `hardware/releases/<variant>/panel/`:
  - `panel.kicad_pcb`, `panel.kicad_pro`, `panel.kicad_dru`
  - `panel_gerbers.zip` (single Gerber + drill upload for JLCPCB)
  - `panel_bom_jlc.csv` (consolidated BOM merging shared LCSC parts across boards)
  - `panel_cpl_jlc.csv` (consolidated Pick-and-Place CPL for the panel)
  - `panel_assembly_check.csv` & `panel_hand_fit.csv`
  - `drc.json` (verified 0 DRC errors, 0 unrouted)
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
from pathlib import Path

import pcbnew

REPO = Path("/work")
SLOT_W = 2.0       # mm routing slot between adjacent sub-boards
TAB_H = 3.2        # mm vertical width of each mouse-bite breakaway tab
HOLE_DIA = 0.5     # mm NPTH mouse-bite drill diameter
HOLE_Y_OFFS = (-0.9, -0.3, 0.3, 0.9)  # 4 mouse-bite holes per tab end (0.6 mm pitch)

# Offset sub-board reference numbers (+100 for ui, +200 for interface) so designators stay
# standard IPC prefixes (R101, C101, D101, U101) — required by Aisler Smart Match (which
# requires resistors to start with 'R', capacitors with 'C', diodes with 'D').
BOARD_REF_OFFSET = {
    "main": 0,
    "ui": 100,
    "interface": 200,
}


def offset_ref(board_name: str, ref: str) -> str:
    off = BOARD_REF_OFFSET.get(board_name, 0)
    if off == 0:
        return ref
    m = re.match(r"^([A-Za-z]+)(\d+)$", ref)
    if not m:
        return f"{board_name.upper()}_{ref}"
    return f"{m.group(1)}{int(m.group(2)) + off}"


def run(*cmd: str) -> None:
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def add_edge_line(pcb: pcbnew.BOARD, x0: float, y0: float, x1: float, y1: float) -> None:
    if abs(x0 - x1) < 1e-4 and abs(y0 - y1) < 1e-4:
        return
    seg = pcbnew.PCB_SHAPE(pcb)
    seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
    seg.SetLayer(pcbnew.Edge_Cuts)
    seg.SetWidth(pcbnew.FromMM(0.1))
    seg.SetStart(pcbnew.VECTOR2I_MM(x0, y0))
    seg.SetEnd(pcbnew.VECTOR2I_MM(x1, y1))
    pcb.Add(seg)


def add_mouse_bite_holes(pcb: pcbnew.BOARD, coords: list[tuple[float, float]]) -> None:
    """Place all mouse-bite NPTH holes inside a single DNP/Excluded footprint so BOM tools ignore them."""
    if not coords:
        return
    fp = pcbnew.FOOTPRINT(pcb)
    fp.SetReference("MOUSE_BITES")
    fp.SetValue("DNP")
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    fp.SetDNP(True)
    fp.SetExcludedFromBOM(True)
    fp.SetExcludedFromPosFiles(True)
    fp.SetPosition(pcbnew.VECTOR2I_MM(0, 0))
    for idx, (x_mm, y_mm) in enumerate(coords, start=1):
        pad = pcbnew.PAD(fp)
        pad.SetNumber(str(idx))
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        pad.SetSize(pcbnew.VECTOR2I_MM(HOLE_DIA, HOLE_DIA))
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(HOLE_DIA, HOLE_DIA))
        pad.SetLayerSet(pad.UnplatedHoleMask())
        pad.SetPosition(pcbnew.VECTOR2I_MM(x_mm, y_mm))
        fp.Add(pad)
    pcb.Add(fp)


def is_vertical_edge_at_x(drw: pcbnew.BOARD_ITEM, x_target: float) -> bool:
    if drw.GetLayer() != pcbnew.Edge_Cuts or not isinstance(drw, pcbnew.PCB_SHAPE):
        return False
    if drw.GetShape() != pcbnew.SHAPE_T_SEGMENT:
        return False
    sx = pcbnew.ToMM(drw.GetStart().x)
    ex = pcbnew.ToMM(drw.GetEnd().x)
    return abs(sx - x_target) < 0.08 and abs(ex - x_target) < 0.08


def board_edge_bounds(brd: pcbnew.BOARD) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for d in brd.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts and isinstance(d, pcbnew.PCB_SHAPE):
            xs.extend((round(pcbnew.ToMM(d.GetStart().x), 4), round(pcbnew.ToMM(d.GetEnd().x), 4)))
            ys.extend((round(pcbnew.ToMM(d.GetStart().y), 4), round(pcbnew.ToMM(d.GetEnd().y), 4)))
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    return x0, y0, x1 - x0, y1 - y0


def build_panel(
    variant: str,
    boards: tuple[str, ...],
    root: Path,
    board_checks: dict[str, list],
) -> list[str]:
    panel_dir = root / "panel"
    shutil.rmtree(panel_dir, ignore_errors=True)
    panel_dir.mkdir(parents=True)

    # Pre-load all boards first so SWIG type descriptors stay clean
    loaded: dict[str, tuple[pcbnew.BOARD, float, float, float, float]] = {}
    for bname in boards:
        bpath = REPO / "hardware/layout" / variant / bname / f"{bname}.kicad_pcb"
        brd = pcbnew.LoadBoard(str(bpath))
        x0, y0, w, h = board_edge_bounds(brd)
        loaded[bname] = (brd, x0, y0, w, h)

    base_name = boards[0]
    base_path = REPO / "hardware/layout" / variant / base_name / f"{base_name}.kicad_pcb"
    for suffix in (".kicad_pro", ".kicad_dru"):
        shutil.copy(base_path.with_suffix(suffix), panel_dir / f"panel{suffix}")

    panel, x0_0, y0_0, w0, h0 = loaded[base_name]
    placements: list[tuple[str, float, float, float, float, float, float]] = [
        (base_name, 0.0, 0.0, x0_0, y0_0, w0, h0)
    ]
    cur_right = x0_0 + w0

    combined_parts: list[dict] = []
    for p in json.loads((REPO / "hardware/build" / variant / base_name / "parts.json").read_text()):
        cp = dict(p)
        cp["ref"] = offset_ref(base_name, p["ref"])
        combined_parts.append(cp)

    for bname in boards[1:]:
        net_prefix = f"{bname.upper()}_"
        src, bx0, by0, bw, bh = loaded[bname]

        target_x0 = round(cur_right + SLOT_W, 4)
        # Align top edge (y_max = 0.0) across all boards on the panel
        dx = round(target_x0 - bx0, 4)
        dy = round((y0_0 + h0) - (by0 + bh), 4)
        target_y0 = round(by0 + dy, 4)
        vec = pcbnew.VECTOR2I_MM(dx, dy)

        # Register prefixed nets on panel
        net_map = {"": panel.FindNet("")}
        for net_name in src.GetNetInfo().NetsByName():
            sname = str(net_name)
            if not sname:
                continue
            pname = f"{net_prefix}{sname}"
            existing = panel.FindNet(pname)
            if not existing:
                ni = pcbnew.NETINFO_ITEM(panel, pname)
                panel.Add(ni)
                existing = panel.FindNet(pname)
            net_map[sname] = existing

        # Transfer footprints
        for fp in list(src.GetFootprints()):
            src.Remove(fp)
            fp.SetReference(offset_ref(bname, fp.GetReference()))
            for pad in fp.Pads():
                orig_net = pad.GetNetname()
                if net_map.get(orig_net):
                    pad.SetNet(net_map[orig_net])
            fp.Move(vec)
            panel.Add(fp)

        # Transfer tracks and vias
        for trk in list(src.GetTracks()):
            src.Remove(trk)
            orig_net = trk.GetNetname()
            if net_map.get(orig_net):
                trk.SetNet(net_map[orig_net])
            trk.Move(vec)
            panel.Add(trk)

        # Transfer copper zones
        for zone in list(src.Zones()):
            src.Remove(zone)
            orig_net = zone.GetNetname()
            if net_map.get(orig_net):
                zone.SetNet(net_map[orig_net])
            zone.Move(vec)
            panel.Add(zone)

        # Transfer all drawings (Edge.Cuts + silkscreen) shifted by vec
        for drw in list(src.GetDrawings()):
            src.Remove(drw)
            drw.Move(vec)
            panel.Add(drw)

        placements.append((bname, dx, dy, target_x0, target_y0, bw, bh))
        cur_right = target_x0 + bw

        for p in json.loads((REPO / "hardware/build" / variant / bname / "parts.json").read_text()):
            cp = dict(p)
            cp["ref"] = offset_ref(bname, p["ref"])
            combined_parts.append(cp)

    # Split ONLY the shared vertical seam edges between board i (x = bx1) and board i+1 (x = next_x0)
    # and bridge them with 2 mouse-bite breakaway tabs + NPTH snap holes
    mb_coords: list[tuple[float, float]] = []
    n = len(placements)
    for i in range(n - 1):
        _, _, _, lx0, ly0, lw, lh = placements[i]
        _, _, _, rx0, ry0, _rw, rh = placements[i + 1]
        lx1 = round(lx0 + lw, 4)
        ly1 = round(ly0 + lh, 4)
        ry1 = round(ry0 + rh, 4)
        ov_y0 = max(ly0, ry0)
        ov_y1 = min(ly1, ry1)
        ov_h = ov_y1 - ov_y0
        t1 = round(ov_y0 + max(6.5, ov_h * 0.25), 4)
        t2 = round(ov_y0 + min(ov_h - 6.5, ov_h * 0.75), 4)
        hw = TAB_H / 2

        for drw in list(panel.GetDrawings()):
            if is_vertical_edge_at_x(drw, lx1) or is_vertical_edge_at_x(drw, rx0):
                panel.Delete(drw)

        # Rebuild right vertical edge of board i with tab openings at t1, t2
        add_edge_line(panel, lx1, ly0, lx1, t1 - hw)
        add_edge_line(panel, lx1, t1 + hw, lx1, t2 - hw)
        add_edge_line(panel, lx1, t2 + hw, lx1, ly1)

        # Rebuild left vertical edge of board i+1 with tab openings at t1, t2
        add_edge_line(panel, rx0, ry0, rx0, t1 - hw)
        add_edge_line(panel, rx0, t1 + hw, rx0, t2 - hw)
        add_edge_line(panel, rx0, t2 + hw, rx0, ry1)

        # Add horizontal tab bridges and 4 NPTH mouse-bite holes per tab end
        hole_off_x = 0.15 if variant != "v2" else 0.55
        for tc in (t1, t2):
            add_edge_line(panel, lx1, tc - hw, rx0, tc - hw)
            add_edge_line(panel, lx1, tc + hw, rx0, tc + hw)
            for dy_h in HOLE_Y_OFFS:
                mb_coords.append((lx1 + hole_off_x, tc + dy_h))
                mb_coords.append((rx0 - hole_off_x, tc + dy_h))

    add_mouse_bite_holes(panel, mb_coords)

    panel_pcb_path = panel_dir / "panel.kicad_pcb"
    pcbnew.SaveBoard(str(panel_pcb_path), panel)

    build_panel_dir = REPO / "hardware/build" / variant / "panel"
    build_panel_dir.mkdir(parents=True, exist_ok=True)
    (build_panel_dir / "parts.json").write_text(json.dumps(combined_parts, indent=2))

    # Run DRC on the combined panel (including mouse-bite NPTHs and breakaway tabs)
    drc_report = panel_dir / "drc.json"
    run("kicad-cli", "pcb", "drc", "--format", "json", "--output", str(drc_report), str(panel_pcb_path))
    drc = json.loads(drc_report.read_text())
    errors = [v for v in drc["violations"] if v["severity"] == "error"]
    unrouted = drc["unconnected_items"]
    problems = (
        [f"panel: {len(errors)} DRC errors: {[e['description'] for e in errors[:5]]}"] * bool(errors)
        + [f"panel: {len(unrouted)} unrouted"] * bool(unrouted)
    )
    if problems:
        return problems

    # Export panel_gerbers.zip
    copper = [pcbnew.LayerName(layer) for layer in panel.GetEnabledLayers().CuStack()]
    layers = copper + ["F.Mask", "B.Mask", "F.Paste", "B.Paste", "F.SilkS", "B.SilkS", "Edge.Cuts"]
    gtarget = panel_dir / "gerbers"
    gtarget.mkdir()
    run("kicad-cli", "pcb", "export", "gerbers", "--output", f"{gtarget}/",
        "--layers", ",".join(layers), "--no-protel-ext", str(panel_pcb_path))
    run("kicad-cli", "pcb", "export", "drill", "--output", f"{gtarget}/",
        "--format", "excellon", "--excellon-separate-th", str(panel_pcb_path))
    shutil.make_archive(str(panel_dir / "panel_gerbers"), "zip", gtarget)
    shutil.rmtree(gtarget)

    # Export top and bottom SVG renders of the breakaway panel
    renders_dir = panel_dir / "renders"
    renders_dir.mkdir(exist_ok=True)
    run("kicad-cli", "pcb", "export", "svg", "--output", str(renders_dir / "top.svg"),
        "--layers", "F.Cu,F.Mask,F.SilkS,Edge.Cuts", "--page-size-mode", "2", str(panel_pcb_path))
    run("kicad-cli", "pcb", "export", "svg", "--output", str(renders_dir / "bottom.svg"),
        "--layers", "B.Cu,B.Mask,B.SilkS,Edge.Cuts", "--mirror", "--page-size-mode", "2", str(panel_pcb_path))

    # Write consolidated panel_bom_jlc.csv, panel_cpl_jlc.csv, panel_assembly_check.csv, panel_hand_fit.csv
    by_ref = {p["ref"]: p for p in combined_parts}
    groups: dict[tuple[str, str, str], list[str]] = {}
    for p in by_ref.values():
        if p["assembly"] == "jlc":
            key = (p["value"], p["footprint"].split(":")[1], p["lcsc"])
            groups.setdefault(key, []).append(p["ref"])
    with open(panel_dir / "panel_bom_jlc.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, footprint, lcsc), refs in sorted(groups.items()):
            w.writerow([value, ",".join(sorted(refs)), footprint, lcsc])

    cpl_rows = []
    check_rows = []
    for bname, dx, dy, _, _, _, _ in placements:
        for c in board_checks.get(bname, []):
            if c.assembly != "jlc":
                continue
            pref = offset_ref(bname, c.ref)
            fp = panel.FindFootprintByReference(pref)
            layer = "Bottom" if fp.IsFlipped() else "Top"
            kicad_rot = round(fp.GetOrientationDegrees()) % 360
            px = c.placement.x + dx
            py = c.placement.y - dy
            cpl_rows.append([pref, f"{px:.3f}mm", f"{py:.3f}mm", layer, c.placement.rotation])
            check_rows.append([
                pref, c.lcsc, by_ref[pref]["mpn"], c.jlc_footprint, layer,
                kicad_rot, c.placement.rotation, c.stock, c.library, "lands pin for pin",
            ])

    with open(panel_dir / "panel_cpl_jlc.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writerows(cpl_rows)

    with open(panel_dir / "panel_assembly_check.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "LCSC", "Manufacturer part", "JLCPCB footprint", "Layer",
                    "KiCad rotation", "JLCPCB rotation", "Stock", "Library", "Result"])
        w.writerows(check_rows)

    with open(panel_dir / "panel_hand_fit.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Value", "Manufacturer part", "Notes"])
        for p in sorted(by_ref.values(), key=lambda item: item["ref"]):
            if p["assembly"] == "hand":
                w.writerow([p["ref"], p["value"], p["mpn"], p["source"]])

    pbb = panel.GetBoardEdgesBoundingBox()
    pw_mm = pcbnew.ToMM(pbb.GetWidth())
    ph_mm = pcbnew.ToMM(pbb.GetHeight())
    print(f"panel ({'+'.join(boards)}): released {pw_mm:.1f}x{ph_mm:.1f}mm breakaway mouse-bite panel "
          f"(0 DRC errors, {len(groups)} consolidated BOM lines, {len(cpl_rows)} SMT placements)")
    return []
