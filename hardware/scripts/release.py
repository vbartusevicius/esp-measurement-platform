"""Package a fabrication release from the stored layouts (`eda` container).

    [HARDWARE_VARIANT=<variant>] python3 hardware/scripts/release.py [<version> [<board>...]]

Naming boards re-releases only those (the others' folders stay as they are);
the assembly parts list and the enclosure are always refreshed.

<version> defaults to the variant's product.release (v1 -> v1, v2 -> v2).

Writes hardware/releases/<version>/<board>/ for every board: KiCad sources,
Gerbers, drill files and the IPC-D-356 test netlist (one zip for upload),
ODB++ and IPC-2581 (with part numbers, for AISLER, Eurocircuits and other
fabs that assemble from them), a fab-neutral BOM and placement list (PCBWay,
Eurocircuits, ...), JLCPCB BOM and placement files for the parts JLCPCB
assembles, an assembly check report, a hand-fit list, a STEP model, renders
and the DRC report. Stops without writing a board when its
DRC has an error or an unrouted connection, when a part is neither orderable
nor hand-fit, or when jlc_parts.py finds a JLC part that is not what the
circuit wants, would not land pin for pin, or is short of stock. Placement
rotations and centres come from that fit, not from KiCad's footprint origin.
Also writes order_lcsc.csv / order_mouser.csv / order_elsewhere.csv
(parts_orders.py) for buying one device's parts to assemble by hand.
Enclosure files are copied from mechanical/build/<variant>/ (1-DIN) and
mechanical/build/<variant>-box/ (wall-mount box) when present.
"""

import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import jlc_parts
import panelize
import parts_orders
import pcbnew
import yaml

REPO = Path("/work")
sys.path.insert(0, str(REPO / "hardware/circuits"))
from product_spec import all_boards, load_spec

SPEC = load_spec()
VARIANT = SPEC["active_variant"]
PANEL_BOARDS = tuple(SPEC["variants"][VARIANT]["boards"])   # the accessory boards are ordered on their own
BOARDS = tuple(all_boards(SPEC, VARIANT))
RELEASE = SPEC["product"]["release"]


def assembly_parts_path():
    variant_list = REPO / "hardware/circuits/variants" / VARIANT / "assembly_parts.yaml"
    return variant_list if variant_list.exists() else REPO / "hardware/product/assembly_parts.yaml"


def run(*cmd):
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def layout_path(board):
    return REPO / "hardware/layout" / VARIANT / board / f"{board}.kicad_pcb"


def parts(board):
    return json.loads((REPO / "hardware/build" / VARIANT / board / "parts.json").read_text())


def assembly_checks(board, *, live=True):
    return jlc_parts.check_board(pcbnew.LoadBoard(str(layout_path(board))), parts(board), live=live)


def gate(board, out, checks):
    report = out / "drc.json"
    run("kicad-cli", "pcb", "drc", "--format", "json", "--output", str(report),
        str(layout_path(board)))
    drc = json.loads(report.read_text())
    errors = [v for v in drc["violations"] if v["severity"] == "error"]
    unsourced = [p["ref"] for p in parts(board)
                 if not (p["assembly"] == "jlc" and p["lcsc"].startswith("C")
                         or p["assembly"] == "hand" and p["mpn"])]
    problems = [f"{len(errors)} DRC errors"] * bool(errors) \
        + [f"{len(drc['unconnected_items'])} unrouted"] * bool(drc["unconnected_items"]) \
        + [f"unsourced parts {unsourced}"] * bool(unsourced) \
        + [f"{c.ref} ({c.lcsc}): {problem}" for c in checks for problem in c.problems]
    return problems


def gerbers(board, out):
    """Gerber X2 + Excellon (plated / non-plated apart) + the job file and the IPC-D-356
    netlist for the electrical test: the data set every fab takes, assembly or not."""
    pcb = pcbnew.LoadBoard(str(layout_path(board)))
    copper = [pcbnew.LayerName(layer) for layer in pcb.GetEnabledLayers().CuStack()]
    layers = copper + ["F.Mask", "B.Mask", "F.Paste", "B.Paste", "F.SilkS", "B.SilkS", "Edge.Cuts"]
    target = out / "gerbers"
    target.mkdir()
    run("kicad-cli", "pcb", "export", "gerbers", "--output", f"{target}/",
        "--layers", ",".join(layers), "--no-protel-ext", str(layout_path(board)))
    run("kicad-cli", "pcb", "export", "drill", "--output", f"{target}/",
        "--format", "excellon", "--excellon-separate-th", str(layout_path(board)))
    run("kicad-cli", "pcb", "export", "ipcd356", "--output", str(target / f"{board}-netlist.ipc"),
        str(layout_path(board)))
    shutil.make_archive(str(out / f"{board}_gerbers"), "zip", target)
    shutil.rmtree(target)


def fab_board(board):
    """A copy of the layout carrying what assembly houses read from CAD data: MPN and
    Manufacturer (and the LCSC number) on every footprint, hand-fit parts flagged Do Not
    Populate. ODB++, IPC-2581 and the placement list come from it; the stored layout and
    its released copy stay as routed."""
    pcb = pcbnew.LoadBoard(str(layout_path(board)))
    by_ref = {p["ref"]: p for p in parts(board)}
    for fp in pcb.GetFootprints():
        p = by_ref.get(fp.GetReference())
        if not p:
            continue
        for name, value in (("MPN", p["mpn"]), ("Manufacturer", p["mfr"]), ("LCSC", p["lcsc"])):
            if value:
                fp.SetField(name, value)
        if p["assembly"] == "hand":
            fp.SetDNP(True)
            fp.SetExcludedFromBOM(True)
            fp.SetExcludedFromPosFiles(True)
    path = REPO / "hardware/build" / VARIANT / board / "fab" / f"{board}.kicad_pcb"
    path.parent.mkdir(parents=True, exist_ok=True)
    pcb.Save(str(path))
    shutil.copy(layout_path(board).with_suffix(".kicad_pro"), path.with_suffix(".kicad_pro"))
    return path


def mount_type(fp):
    return "THT" if fp.GetAttributes() & pcbnew.FP_THROUGH_HOLE else "SMD"


def generic_assembly_files(board, out):
    """Fab-neutral assembly data: ODB++ (AISLER assembles from it; MPN fields auto-assign
    parts), IPC-2581 with its BOM, and a CSV BOM + placement list in the column names
    PCBWay, Eurocircuits and most assemblers expect. Coordinates are those of the Gerbers;
    rotations follow KiCad's footprint zero orientation (confirm in the fab's preview)."""
    fab = fab_board(board)
    run("kicad-cli", "pcb", "export", "odb", "--output", str(out / f"{board}_odb.zip"),
        "--compression", "zip", "--units", "mm", str(fab))
    run("kicad-cli", "pcb", "export", "ipc2581", "--output", str(out / f"{board}_ipc2581.zip"), "--compress",
        "--bom-col-mfg-pn", "MPN", "--bom-col-mfg", "Manufacturer", "--bom-col-dist-pn", "LCSC",
        "--bom-col-dist", "LCSC", str(fab))

    pcb = pcbnew.LoadBoard(str(fab))
    fps = {fp.GetReference(): fp for fp in pcb.GetFootprints()}
    groups = {}
    for p in parts(board):
        key = (p["assembly"] == "hand", p["mfr"], p["mpn"], p["value"], p["footprint"].split(":")[1])
        groups.setdefault(key, []).append(p)
    with open(out / f"{board}_bom.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Item", "Qty", "Designator", "Value", "Manufacturer", "MPN", "LCSC", "Package", "Type",
                    "Place", "Description"])
        for item, ((hand, mfr, mpn, value, package), group) in enumerate(sorted(groups.items()), start=1):
            refs = sorted(p["ref"] for p in group)
            w.writerow([item, len(refs), ",".join(refs), value, mfr, mpn, group[0]["lcsc"], package,
                        mount_type(fps[refs[0]]), "NO" if hand else "YES",
                        ("Hand-fitted after assembly: " if hand else "") + group[0]["source"]])

    pos = REPO / "hardware/build" / VARIANT / board / "fab" / f"{board}-pos.csv"
    run("kicad-cli", "pcb", "export", "pos", "--output", str(pos), "--format", "csv", "--units", "mm",
        "--side", "both", "--exclude-dnp", str(fab))
    with open(pos, newline="") as f, open(out / f"{board}_cpl.csv", "w", newline="") as o:
        w = csv.writer(o)
        w.writerow(["Designator", "Mid X", "Mid Y", "Rotation", "Layer", "Value", "Package", "Type"])
        for r in sorted(csv.DictReader(f), key=lambda r: r["Ref"]):
            w.writerow([r["Ref"], f"{float(r['PosX']):.3f}", f"{float(r['PosY']):.3f}", f"{float(r['Rot']):.1f}",
                        "Top" if r["Side"] == "top" else "Bottom", r["Val"], r["Package"], mount_type(fps[r["Ref"]])])


def assembly_files(board, out, checks):
    checks = [c for c in checks if c.assembly == "jlc"]
    by_ref = {p["ref"]: p for p in parts(board)}
    groups = {}
    for p in by_ref.values():
        if p["assembly"] == "jlc":
            key = (p["value"], p["footprint"].split(":")[1], p["lcsc"])
            groups.setdefault(key, []).append(p["ref"])
    with open(out / f"{board}_bom_jlc.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, footprint, lcsc), refs in sorted(groups.items()):
            w.writerow([value, ",".join(sorted(refs)), footprint, lcsc])
    pcb = pcbnew.LoadBoard(str(layout_path(board)))
    with open(out / f"{board}_cpl_jlc.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for c in checks:
            layer = "Bottom" if pcb.FindFootprintByReference(c.ref).IsFlipped() else "Top"
            w.writerow([c.ref, f"{c.placement.x:.3f}mm", f"{c.placement.y:.3f}mm", layer, c.placement.rotation])
    turned, bottom = [], []
    with open(out / f"{board}_assembly_check.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "LCSC", "Manufacturer part", "JLCPCB footprint", "Layer",
                    "KiCad rotation", "JLCPCB rotation", "Stock", "Library", "Result"])
        for c in checks:
            fp = pcb.FindFootprintByReference(c.ref)
            kicad = round(fp.GetOrientationDegrees()) % 360
            layer = "Bottom" if fp.IsFlipped() else "Top"
            w.writerow([c.ref, c.lcsc, by_ref[c.ref]["mpn"], c.jlc_footprint, layer, kicad,
                        c.placement.rotation, c.stock, c.library, "lands pin for pin"])
            if c.placement.rotation != kicad:
                turned.append(c.ref)
            if fp.IsFlipped():
                bottom.append(c.ref)
    with open(out / f"{board}_hand_fit.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Value", "Manufacturer part", "Notes"])
        for p in sorted(by_ref.values(), key=lambda p: p["ref"]):
            if p["assembly"] == "hand":
                w.writerow([p["ref"], p["value"], p["mpn"], p["source"]])
    return turned, bottom


def release_board(board, root):
    out = root / board
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    checks = assembly_checks(board)
    problems = gate(board, out, checks)
    if problems:
        shutil.rmtree(out)
        return problems, ([], []), []
    for suffix in (".kicad_pcb", ".kicad_pro", ".kicad_dru"):
        shutil.copy(layout_path(board).with_suffix(suffix), out)
    gerbers(board, out)
    generic_assembly_files(board, out)
    placement = assembly_files(board, out, checks)
    step = REPO / "hardware/build" / VARIANT / board / f"{board}.step"
    run("kicad-cli", "pcb", "export", "step", "--grid-origin", "--subst-models", "--force",
        "--output", str(step), str(layout_path(board)))
    shutil.copy(step, out)
    run("python3", str(REPO / "hardware/scripts/render_board.py"), board, "release")
    renders = REPO / "hardware/build" / VARIANT / board / "render/release"
    shutil.copytree(renders, out / "renders", ignore=shutil.ignore_patterns("drc.json", "zoom_*"))
    return [], placement, checks


def main(version, boards=BOARDS):
    root = REPO / "hardware/releases" / version
    root.mkdir(parents=True, exist_ok=True)
    failed = False
    board_checks = {}
    for board in boards:
        problems, (turned, bottom), checks = release_board(board, root)
        board_checks[board] = checks
        if problems:
            failed = True
            print(f"{board}: NOT released:")
            for problem in problems:
                print(f"  {problem}")
        else:
            print(f"{board}: released; every JLC part lands pin for pin. Rotation differs from KiCad's "
                  f"for {', '.join(turned) or 'none'}; bottom side: {', '.join(bottom) or 'none'} "
                  "(confirm these in JLCPCB's placement preview)")
    if not failed and set(PANEL_BOARDS) <= set(boards):
        panel_problems = panelize.build_panel(VARIANT, PANEL_BOARDS, root, board_checks)
        if panel_problems:
            failed = True
            for problem in panel_problems:
                print(f"  {problem}")
    with open(root / "assembly_parts.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Item", "Qty", "Part", "Description", "Source"])
        for p in yaml.safe_load(assembly_parts_path().read_text()):
            w.writerow([p["item"], p["qty"], p["part"], p["description"], p["source"]])
    # Self-assembly orders for one device, checked live against LCSC (stock there differs from JLC's)
    lcsc_rows = parts_orders.write(root)
    for problem in parts_orders.check_live(lcsc_rows):
        print(f"  order_lcsc.csv: {problem}")
    enclosure = REPO / "mechanical/build" / VARIANT
    if enclosure.exists():
        shutil.copytree(enclosure, root / "enclosure", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("fit_*.png", "front_legend.png"))
    wall_box = REPO / "mechanical/build" / f"{VARIANT}-box"
    if wall_box.exists():
        shutil.copytree(wall_box, root / "box_enclosure", dirs_exist_ok=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else RELEASE, tuple(sys.argv[2:]) or BOARDS))
