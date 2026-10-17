"""The hardware variant under test (HARDWARE_VARIANT, default v1) and the
paths of its stored boards and generated netlists."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "hardware/circuits"))
from product_spec import load_spec

SPEC = load_spec()
VARIANT = SPEC["active_variant"]
BOARDS = tuple(SPEC["variants"][VARIANT]["boards"])


def layout_path(board, suffix=".kicad_pcb"):
    return REPO / "hardware/layout" / VARIANT / board / f"{board}{suffix}"


def build_path(board, name):
    return REPO / "hardware/build" / VARIANT / board / name


def layout_plan(board):
    import yaml

    return yaml.safe_load((REPO / "hardware/circuits/variants" / VARIANT / f"layout_{board}.yaml").read_text())
