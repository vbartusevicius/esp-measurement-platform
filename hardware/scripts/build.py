"""Unified hardware & mechanical build, route, render, release and test pipeline.

From the host:
    python3 hardware/scripts/build.py             # full build + release + tests for v1
    python3 hardware/scripts/build.py --eda       # circuits + placement/routing + board renders
    python3 hardware/scripts/build.py --cad       # 1-DIN enclosure + plugin accessories + 3D renders
    python3 hardware/scripts/build.py --release   # package hardware/releases/v1/
    python3 hardware/scripts/build.py --test      # run full EDA + CAD pytest suites
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ALL_VARIANTS = ("v1",)


def has_module(name):
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def run_eda(boards, *, fresh=False, do_release=False, do_test=False):
    sys.path.insert(0, str(REPO / "hardware/scripts"))
    import gen_circuits
    import layout
    import pcbnew
    import release
    import render_board

    gen_circuits.main()
    os.chdir(REPO)
    variant = layout.VARIANT
    target_boards = boards or layout.SPEC["variants"][variant]["boards"]
    for b in target_boards:
        pcb_path = layout.stored_board_path(b)
        if fresh and pcb_path.exists():
            pcb_path.unlink()
        layout.sync(b)
        board = pcbnew.LoadBoard(str(pcb_path))
        if len(list(board.GetTracks())) == 0 or fresh:
            layout.route(b)
        layout.tidy_silk(b)
        render_board.render(b, "routed", placement=False)
    if do_release:
        release.main(variant, target_boards)
    if do_test:
        subprocess.run([
            sys.executable, "-m", "pytest",
            "hardware/tests", "mechanical/tests/test_fit.py",
            "-q", "-p", "no:cacheprovider",
        ], cwd=REPO, check=True)


def run_cad(*, do_test=False):
    sys.path.insert(0, str(REPO / "mechanical/scripts"))
    import build_distance_pod
    import build_enclosure
    import build_radiation_duct
    import fit_drawing
    import front_legend
    import legend_color_model
    import render_assembly3d

    build_enclosure.export_parts(REPO / "mechanical/build" / build_enclosure.VARIANT)
    fit_drawing.main()
    front_legend.main()
    legend_color_model.main()
    render_assembly3d.main()
    build_radiation_duct.main()
    build_distance_pod.main()
    if do_test:
        subprocess.run([
            sys.executable, "-m", "pytest",
            "mechanical/tests/test_enclosure_probe.py",
            "mechanical/tests/test_front_legend.py",
            "mechanical/tests/test_accessories.py",
            "-q", "-p", "no:cacheprovider",
        ], cwd=REPO, check=True)


def docker_run(variant, service, cmd):
    full = ["docker", "compose", "--profile", "hardware", "run", "--rm", "-T",
            "-e", f"HARDWARE_VARIANT={variant}", service, cmd]
    proc = subprocess.run(full, cwd=REPO, text=True, capture_output=True, check=False)
    for line in (proc.stdout + proc.stderr).splitlines():
        if not any(skip in line for skip in ("Container ", "platform (", "Debug: ", 'assert "Pgm')):
            print(f"[{variant} {service}] {line}")
    if proc.returncode != 0:
        raise RuntimeError(f"{variant} {service} failed (exit {proc.returncode})")


def run_variant_on_host(variant, args):
    run_all = not (args.eda or args.cad or args.release or args.test)
    board_arg = " ".join(args.boards)
    fresh_flag = " --fresh" if args.fresh else ""
    if args.eda or run_all:
        docker_run(variant, "eda", f"python3 hardware/scripts/build.py --in-eda{fresh_flag} {board_arg}".strip())
    if args.cad or run_all:
        docker_run(variant, "cad", "python3 hardware/scripts/build.py --in-cad")
    if args.release or run_all:
        docker_run(variant, "eda", f"python3 hardware/scripts/release.py {variant} {board_arg}".strip())
    if args.test or run_all:
        docker_run(variant, "eda",
                   "python3 -m pytest hardware/tests mechanical/tests/test_fit.py -q -p no:cacheprovider --tb=short")
        docker_run(variant, "cad",
                   "python3 -m pytest mechanical/tests/test_enclosure_probe.py "
                   "mechanical/tests/test_front_legend.py mechanical/tests/test_accessories.py "
                   "-q -p no:cacheprovider --tb=short")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("variants", nargs="*", help="v1 (or board names when inside a container)")
    parser.add_argument("--boards", nargs="*", default=[], help="subset of boards (e.g. main ui)")
    parser.add_argument("--eda", action="store_true", help="run circuit generation + layout/routing + board renders")
    parser.add_argument("--cad", action="store_true", help="run enclosure + accessories + 3MF/embossed + 3D renders")
    parser.add_argument("--release", action="store_true", help="run release.py")
    parser.add_argument("--test", action="store_true", help="run EDA + CAD pytest suites")
    parser.add_argument("--fresh", action="store_true", help="re-place and re-route boards from scratch")
    parser.add_argument("--in-eda", action="store_true", help="run EDA steps directly inside the eda container")
    parser.add_argument("--in-cad", action="store_true", help="run CAD steps directly inside the cad container")
    args = parser.parse_args()

    if args.in_eda or has_module("pcbnew"):
        boards = [v for v in args.variants if v not in ALL_VARIANTS] or args.boards
        run_eda(boards, fresh=args.fresh, do_release=args.release, do_test=args.test)
        return
    if args.in_cad or has_module("cadquery"):
        run_cad(do_test=args.test)
        return

    variants = [v for v in args.variants if v in ALL_VARIANTS] or list(ALL_VARIANTS)
    for v in variants:
        run_variant_on_host(v, args)


if __name__ == "__main__":
    main()
