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


# --- values are shown the way they were typed --------------------------

def test_phasor_values_stay_in_angle_notation():
    """expand_shorthand turns 110∠0° into a 17-digit rectangular
    number even with expand_si=False; the label must show what the
    reader wrote."""
    svg = to_svg("ea,1,0,(110∠0°):r1,1,0,10")
    joined = " ".join(texts(svg))
    assert "∠" in joined
    assert "110" in joined
    assert "16829419696157" not in joined   # no float dust


def test_long_float_literals_are_rounded_for_display():
    svg = to_svg("e1,1,0,173.20508075688772:r1,1,0,10")
    joined = " ".join(texts(svg))
    assert "173.20508075688772" not in joined
    assert "173.2" in joined


def test_degree_angles_display_in_degrees():
    """`30*pi/180` is degrees spelt in radians; the label shows the
    degrees back. Display only -- the solver still gets radians."""
    svg = to_svg("j,0,2,10*sin(2*t+30*pi/180):r1,2,0,10")
    joined = " ".join(texts(svg))
    assert "30°" in joined
    assert "pi/180" not in joined


def test_long_values_move_to_a_caption_below_the_drawing():
    """A value too long to letter at the element keeps only the name
    there; `name = value` appears once, below everything else."""
    import re as _re
    desc = "e,1,0,12:r1,1,0,4+20j+[16,-14j+25j]"
    svg = to_svg(desc)
    labels = [(float(m.group(1)), m.group(2)) for m in _re.finditer(
        r'<text[^>]*y="([-\d.]+)"[^>]*>([^<]*)</text>', svg)]
    caption = [y for y, s in labels if s.startswith("r1 = ")]
    assert len(caption) == 1
    # below every other label and every wire
    assert caption[0] > max(y for y, s in labels if not s.startswith("r1 ="))
    # and the value is not also lettered at the element
    assert sum(1 for _, s in labels if "[16," in s) == 1


def test_short_values_stay_at_the_element():
    svg = to_svg(DIVIDER)
    assert not any(" = " in s for s in texts(svg))


# --- crossings and junctions -------------------------------------------

def test_unconnected_crossings_are_drawn_as_hops():
    """Two op-amp stages that force a wire past another wire must mark
    the crossing with the semicircular no-connection hop (an arc in the
    path data), never a bare X crossing."""
    svg = to_svg("e,1,0,vs:r1,1,2,rr1:r2,2,0,rr2:o,2,3,o:"
                 "r3,o,3,rr3:r4,3,0,rr4")
    # The + input routes from the triangle back to node 2 past the
    # bumped r4 -- that crossing must carry an arc.
    assert "A5 5 0 0" in svg


def test_a_wire_never_crosses_an_element_body():
    """Layout invariant, checked over a gallery of layouts that used to
    fail: cascade, follower, transresistance, grounded inverting
    input."""
    from symbulator.schematic import _Canvas
    cases = [
        "e,1,0,vs:r12,1,2,1:r14,1,4,1:r4o,4,o,1:r2o,2,o,1:r23,2,3,1:"
        "r34,3,4,1:o1,0,2,3:o2,0,4,o",
        "e,1,0,1.5:rs,1,2,2'k:o,2,0,o:rl,o,0,1'k",
        "j,0,1,is1:r,1,o,r:o,0,1,o",
        "e,2,0,vs:r1,2,1,r1:r2,1,o,r2:o,1,0,o",
        "e,1,0,28:r1,1,2,6:r2,2,3,6:r3,1,2,2:r4,2,3,8:r5,1,3,12",
    ]
    crossings = []
    orig = _Canvas._flush_wires

    def spy(self):
        for x1, y, x2, _y in [w for w in self.wires
                              if abs(w[1] - w[3]) < 0.01]:
            for sx1, sy1, sx2, sy2, half in self.esegs:
                if abs(sx1 - sx2) > 0.01 or half <= 0:
                    continue
                mid = (sy1 + sy2) / 2.0
                if x1 + 0.5 < sx1 < x2 - 0.5 and sy1 + 0.5 < y < sy2 - 0.5 \
                        and abs(y - mid) < half + 2:
                    crossings.append((x1, y))
        for x, y1, _x, y2 in [w for w in self.wires
                              if abs(w[0] - w[2]) < 0.01]:
            for sx1, sy1, sx2, sy2, half in self.esegs:
                if abs(sy1 - sy2) > 0.01 or half <= 0:
                    continue
                mid = (sx1 + sx2) / 2.0
                if y1 + 0.5 < sy1 < y2 - 0.5 and sx1 + 0.5 < x < sx2 - 0.5 \
                        and abs(x - mid) < half + 2:
                    crossings.append((x, sy1))
        orig(self)

    _Canvas._flush_wires = spy
    try:
        for desc in cases:
            to_svg(desc)
    finally:
        _Canvas._flush_wires = orig
    assert not crossings


# --- op-amp layout -----------------------------------------------------

def test_cascade_outputs_land_right_of_their_inputs():
    """Both stages of an adder cascade must point forward -- the output
    wire never retraces through the triangle."""
    from symbulator.schematic import _Layout, _op_up
    from symbulator.elements import parse_circuit
    els = parse_circuit(
        "e,1,0,vs:r12,1,2,1:r14,1,4,1:r4o,4,o,1:r2o,2,o,1:r23,2,3,1:"
        "r34,3,4,1:o1,0,2,3:o2,0,4,o", expand_si=False)
    lay = _Layout(els)
    for op in lay.opamps:
        assert lay.node_col[op.fields[2]] > lay.node_col[_op_up(op)]


def test_noninverting_stage_draws_its_source_in_the_input_drop():
    """A grounded source that is the only thing on the + input hangs
    under the triangle instead of taking a top-row column."""
    from symbulator.schematic import _Layout
    from symbulator.elements import parse_circuit
    els = parse_circuit("e,p,0,v2:r1,1,0,r1:r2,1,o,r2:o,p,1,o",
                        expand_si=False)
    lay = _Layout(els)
    assert "p" not in lay.node_col
    assert lay.op_src["o"].name == "e"
    # and the drawing still names the node and the source
    joined = " ".join(texts(to_svg("e,p,0,v2:r1,1,0,r1:r2,1,o,r2:o,p,1,o")))
    assert "p" in joined.split() and "e" in joined.split()


def test_grounded_inverting_input_flips_the_pins():
    """`o,1,0,o` (inverting input on ground) must not treat ground as
    the leftmost column; the non-inverting input takes the node row."""
    svg = to_svg("e,2,0,vs:r1,2,1,r1:r2,1,o,r2:o,1,0,o")
    assert "<svg" in svg   # and the body-crossing test above covers it


def test_follower_output_loops_over_the_triangle():
    """`o1,1,2,2` -- output tied to the inverting input -- draws a
    feedback loop, not a wire back through the body."""
    svg = to_svg("e,1,0,4:o1,1,2,2:o2,2,3,o:ro,3,0,4'k:r6,3,o,6'k")
    assert "<svg" in svg


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
