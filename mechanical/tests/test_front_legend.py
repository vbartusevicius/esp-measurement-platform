"""The front legend artwork: every label lies on one flat face, clear of the
openings and the other labels."""

import sys
from itertools import pairwise
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "mechanical/scripts"))
import enclosure_features as ef
import front_legend as fl


@pytest.fixture(scope="module")
def labels():
    return fl.labels()


def test_every_label_sits_on_one_face(labels):
    assert not [lb.text for lb in labels if not any(fl.inside(lb.box(), f) for f in fl.faces().values())]


def test_labels_clear_openings_and_each_other(labels):
    boxes = [lb.box() for lb in labels]
    hits = [lb.text for lb in labels for _, *o in fl.openings() if fl.overlaps(lb.box(), o)]
    pairs = [(a.text, b.text) for i, a in enumerate(labels) for b in labels[i + 1:] if fl.overlaps(a.box(), b.box())]
    assert not hits and not pairs, (hits, pairs, len(boxes))


def test_colour_inlays_fill_exactly_what_they_cut_from_the_cover():
    import build_enclosure as be
    import legend_color_model as lcm

    legend = lcm.legend_bodies()
    cover = be.build_cover()
    removed = cover.val().Volume() - cover.cut(legend).val().Volume()
    assert removed == pytest.approx(legend.val().Volume(), rel=1e-4)


def test_led_labels_keep_their_distance(labels):
    names = {led["id"].upper() for led in ef.SPEC["front_ui"]["leds"]}
    row = sorted((lb for lb in labels if lb.text in names and fl.face_of(lb.y) == "front"), key=lambda lb: lb.x)
    assert len(row) == 3
    assert all(b.box()[0] - a.box()[2] >= 0.8 for a, b in pairwise(row))
