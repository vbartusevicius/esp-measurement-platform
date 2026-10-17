"""The committed boards are fully routed and pass KiCad's DRC with the
project rules written next to them."""

import json
import subprocess

import pytest
from board_variant import BOARDS, layout_path


@pytest.fixture(scope="module", params=BOARDS)
def drc(request, tmp_path_factory):
    board = layout_path(request.param)
    report = tmp_path_factory.mktemp(request.param) / "drc.json"
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all",
                    "--output", str(report), str(board)],
                   capture_output=True, check=False)
    return json.loads(report.read_text())


def test_no_drc_errors(drc):
    errors = [f"{v['type']}: {v['description']}" for v in drc["violations"] if v["severity"] == "error"]
    assert not errors


def test_no_unrouted_connections(drc):
    assert not drc["unconnected_items"]
