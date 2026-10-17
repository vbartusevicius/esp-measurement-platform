"""The stored board layouts must match their netlists exactly, and every part
must be orderable or explicitly hand-fitted."""

import json
import re

import pcbnew
import pytest
from board_variant import BOARDS, SPEC, build_path, layout_path


def sexpr(text):
    stack, current = [], []
    for token in re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text):
        if token == "(":
            stack.append(current)
            current = []
        elif token == ")":
            stack[-1].append(current)
            current = stack.pop()
        else:
            current.append(token.strip('"'))
    return current[0]


def field(node, name):
    return next(item[1] for item in node if isinstance(item, list) and item[0] == name)


def section(tree, name):
    return next(item for item in tree if isinstance(item, list) and item[0] == name)[1:]


def netlist(board):
    tree = sexpr(build_path(board, f"{board}.net").read_text())
    parts = {field(c, "ref"): field(c, "footprint") for c in section(tree, "components")
             if not field(c, "ref").startswith("#")}
    pins = {}
    for net in section(tree, "nets"):
        for node in (n for n in net if isinstance(n, list) and n[0] == "node"):
            if not field(node, "ref").startswith("#"):
                pins[(field(node, "ref"), field(node, "pin"))] = field(net, "name")
    return parts, pins


def layout(board):
    path = layout_path(board)
    if not path.exists():
        pytest.skip(f"{path} not found")
    return pcbnew.LoadBoard(str(path))


@pytest.mark.parametrize("board", BOARDS)
def test_every_netlist_pin_has_a_pad(board):
    _parts, pins = netlist(board)
    pads = {(fp.GetReference(), pad.GetNumber())
            for fp in layout(board).Footprints() for pad in fp.Pads()}
    missing = sorted(key for key in pins if key not in pads)
    assert not missing, f"netlist pins without a footprint pad: {missing}"


@pytest.mark.parametrize("board", BOARDS)
def test_board_matches_netlist(board):
    parts, pins = netlist(board)
    pcb = layout(board)
    footprints = {fp.GetReference(): f"{fp.GetFPID().GetLibNickname()}:{fp.GetFPID().GetLibItemName()}"
                  for fp in pcb.Footprints()}
    assert footprints == parts
    pad_nets = {(fp.GetReference(), pad.GetNumber()): pad.GetNetname()
                for fp in pcb.Footprints() for pad in fp.Pads() if pad.GetNetname()}
    wrong = {k: (v, pad_nets.get(k)) for k, v in pins.items() if pad_nets.get(k) != v}
    assert not wrong, f"pads whose net differs from the netlist: {wrong}"


@pytest.mark.parametrize("board", BOARDS)
def test_every_part_is_sourced(board):
    parts = json.loads(build_path(board, "parts.json").read_text())
    unsourced = [p["ref"] for p in parts
                 if p["assembly"] == "jlc" and not p["lcsc"].startswith("C")
                 or p["assembly"] == "hand" and not p["mpn"]]
    assert not unsourced, f"parts without an LCSC number or hand-fit MPN: {unsourced}"


LINKS = [link for link in SPEC["boards"].get("interconnects", []) if "refs" in link]


@pytest.mark.parametrize("link", LINKS, ids=lambda link: "-".join(f"{b}.{r}" for b, r in link["refs"].items()))
def test_board_links_connect_matching_nets_pin_for_pin(link):
    sides = [{pin: net for (ref, pin), net in netlist(board)[1].items() if ref == conn}
             for board, conn in link["refs"].items()]
    connected = sum(1 for s in link.get("signals", [None] * link["pins"]) if s is not None) \
        if "signals" in link else link["pins"]
    assert len(sides[0]) == len(sides[1]) == connected
    assert sides[0] == sides[1]
    if "signals" in link:
        assert [sides[0].get(str(i + 1)) for i in range(link["pins"])] == link["signals"]
