"""
Schematic drawing: what the SVG must contain for each element type, and
what the documented limitations actually do.

These are structural rather than pixel tests. Asserting exact
coordinates would freeze the layout and break on every spacing tweak;
asserting that a resistor produces a resistor body, that a source
carries its polarity the way the engine stamps it, and that a parallel
pair does not overlap, is what a later refactor must not break.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import re

import pytest

from symbulator.schematic import to_svg, draw
from symbulator.elements import CircuitError


DIVIDER = "e1,1,0,12:r1,1,2,4:r2,2,0,4"


def texts(svg):
    """The label strings in a drawing, in document order."""
    return re.findall(r"<text[^>]*>([^<]*)</text>", svg)


# --- the shape of the output ------------------------------------------

def test_output_is_a_standalone_svg():
    svg = to_svg(DIVIDER)
    assert svg.lstrip().startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg
    assert "viewBox" in svg


def test_every_stroke_defers_to_css():
    """One drawing has to work in both themes, so nothing may name a
    colour of its own."""
    svg = to_svg(DIVIDER)
    assert "currentColor" in svg
    for attr in re.findall(r'(?:stroke|fill)="([^"]+)"', svg):
        assert attr in ("currentColor", "none"), attr


def test_labels_name_every_element():
    svg = to_svg(DIVIDER)
    joined = " ".join(texts(svg))
    for name in ("e1", "r1", "r2"):
        assert name in joined


# --- element bodies ----------------------------------------------------

@pytest.mark.parametrize("desc,name", [
    ("e1,1,0,5:r1,1,0,100", "r1"),
    ("e1,1,0,5:c1,1,0,1e-6", "c1"),
    ("e1,1,0,5:l1,1,0,1e-3", "l1"),
    ("j1,0,1,1:r1,1,0,100", "j1"),
    ("e1,1,0,5:s1,1,0", "s1"),
])
def test_each_element_type_draws_and_is_labelled(desc, name):
    svg = to_svg(desc)
    assert name in " ".join(texts(svg))
    assert svg.count("<path") + svg.count("<line") + svg.count("<circle") > 1


def test_two_port_blocks_draw_as_labelled_boxes():
    """A documented limitation: they render, without port parameters."""
    svg = to_svg("e1,1,0,5:z1,1,2:r1,2,0,50")
    assert "z1" in " ".join(texts(svg))


# --- things the engine decides, not the drawing ------------------------

def test_source_polarity_is_drawn_and_follows_terminal_order():
    """engine._stamp_e stamps v(n1) - v(n2), so + belongs on the n1 end.
    The marks are strokes, not glyphs, so the test is that they exist and
    that reversing the terminals moves them -- if orientation ever stopped
    mattering, the drawing would be lying about the sign of every answer."""
    svg = to_svg("e1,1,0,12:r1,1,0,4")
    two_stroke = [d for d in re.findall(r'<path d="([^"]+)"', svg)
                  if d.count("M") == 2]
    assert two_stroke, "no + mark drawn on the source"
    assert svg != to_svg("e1,0,1,12:r1,1,0,4")


def test_coupled_inductors_are_captioned_not_wired_together():
    """m couples two elements, not two nodes; a dashed tie between coils
    just reads as another wire, so the coupling is written above."""
    svg = to_svg("e1,1,0,5:l1,1,0,1e-3:l2,2,0,1e-3:r1,2,0,50:m1,l1,l2,1e-4")
    joined = " ".join(texts(svg))
    assert "l1" in joined and "l2" in joined
    assert "m1" in joined or "M" in joined


def test_negative_coupling_keeps_the_dots_and_shows_its_sign():
    """Reversed coupling is a negative M -- engine.py adds +M*i_other with
    no orientation term -- so the dots never move and the sign has to be
    visible in the caption instead."""
    svg = to_svg("e1,1,0,5:l1,1,0,1e-3:l2,2,0,1e-3:r1,2,0,50:m1,l1,l2,-1e-4")
    assert "−" in " ".join(texts(svg)) or "-" in " ".join(texts(svg))


# --- layout properties, not coordinates --------------------------------

def test_parallel_elements_do_not_share_a_row():
    """The interval colouring exists for this case: two elements across
    the same pair of nodes must be drawn on different rows."""
    svg = to_svg("e1,1,0,5:r1,1,0,100:r2,1,0,200")
    ys = [float(m) for m in re.findall(r'<line[^>]*y1="([-\d.]+)"', svg)]
    assert len(set(round(y) for y in ys)) > 1


def test_an_element_spanning_an_intermediate_node_is_lifted():
    """A bridge draws as a ladder with a jumper over the top -- a
    documented limitation, and the reason the stacking exists at all."""
    svg = to_svg("e1,1,0,5:r1,1,2,1:r2,2,0,1:r3,1,0,1")
    # Wires are merged where collinear, so count strokes of any kind:
    # the lifted branch still needs risers beyond a flat ladder's wiring.
    assert svg.count("<line") + svg.count("<path") > 6


def test_a_chain_comes_out_as_a_chain():
    ladder = to_svg("e1,1,0,5:r1,1,2,1:r2,2,3,1:r3,3,0,1")
    assert all(n in " ".join(texts(ladder)) for n in ("r1", "r2", "r3"))


def test_opamp_stage_draws():
    svg = to_svg("e1,1,0,1:r1,1,2,1'k:r2,2,3,4'k:o1,0,2,3")
    assert "o1" in " ".join(texts(svg))


# --- input handling ----------------------------------------------------

def test_si_shorthand_is_not_negotiated():
    """to_svg parses with expand_si=False, so a bare 1k draws where the
    solver would stop and ask which it meant. This is what lets the card
    render a circuit that does not solve."""
    assert "<svg" in to_svg("e1,1,0,5:r1,1,0,1k")


def test_newline_separated_description_is_accepted():
    assert to_svg(DIVIDER) == to_svg(DIVIDER.replace(":", "\n"))


def test_a_circuit_without_ground_is_refused():
    with pytest.raises(CircuitError):
        to_svg("r1,1,2,100")


def test_draw_returns_something_renderable():
    out = draw(DIVIDER)
    assert out is not None
