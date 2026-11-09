"""The front legend artwork: every label lies on one flat face, clear of the
openings and the other labels."""

import sys
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


def test_engraving_removes_exactly_the_legend_bodies_from_the_cover():
    import build_enclosure as be
    import legend_engraving as lcm

    legend = lcm.legend_bodies()
    cover = be.build_cover()
    removed = cover.val().Volume() - cover.cut(legend).val().Volume()
    assert removed == pytest.approx(legend.val().Volume(), rel=1e-4)


def test_leds_carry_no_words_or_rings(labels):
    """3 mm words do not fit three LEDs on the 18 mm face; the release README gives the order."""
    names = {led["id"].upper() for led in ef.SPEC["front_ui"]["leds"]}
    assert not names & {lb.text for lb in labels}
    import legend_engraving
    assert len(ef.led_windows()) == 3 and not hasattr(legend_engraving, "led_ring")
