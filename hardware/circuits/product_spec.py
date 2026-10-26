import copy
import os
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
BASE_PATH = REPO / "hardware/product/spec.yaml"


def spec_path():
    variant = os.environ.get("HARDWARE_VARIANT", "v1")
    if variant == "v1":
        return BASE_PATH
    if not variant.isidentifier():
        raise ValueError(f"Invalid hardware variant: {variant}")
    return REPO / "hardware/circuits/variants" / variant / "spec.yaml"


def merge(base, overrides):
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def all_boards(spec, variant):
    """The enclosure boards (panelised together) followed by the accessory
    boards, which are generated, checked and released the same way but
    ordered separately."""
    v = spec["variants"][variant]
    return list(v["boards"]) + list(v.get("accessory_boards", []))


def load_spec():
    base = yaml.safe_load(BASE_PATH.read_text())
    selected = spec_path()
    return base if selected == BASE_PATH else merge(base, yaml.safe_load(selected.read_text()))
