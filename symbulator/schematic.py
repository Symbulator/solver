"""SVG schematic drawing for Symbulator circuit descriptions.

Turns a circuit description -- the same string `dc()`, `ac()`, `fd()`
and `tr()` already take -- into a standalone SVG drawing. Pure standard
library: no matplotlib, no LaTeX, no external toolchain, so it runs
unchanged in CPython and under Pyodide in the browser builds.

The layout is deliberately *not* a general graph-drawing algorithm.
Force-directed placement (Kamada-Kawai and friends, what most netlist
viewers reach for) gives a physics-plausible blob rather than something
that reads like a schematic. This instead assumes the shape that nearly
every linear teaching circuit already has:

  * ground is one horizontal rail along the bottom;
  * an element with one terminal on ground is drawn vertically, between
    the top row of nodes and that rail;
  * an element between two non-ground nodes is drawn horizontally along
    the top row;
  * nodes are ordered left to right by a depth-first walk from the first
    node mentioned, so a chain of elements comes out as a chain;
  * anything that would collide on the top row -- a parallel element, or
    one reaching over an intermediate node -- is lifted onto its own row
    above, with risers back down at each end.

Dividers, ladders, series RLC, T networks and single-op-amp stages land
in their textbook form. See LIMITATIONS at the bottom of this module for
what doesn't.

Colours are left to CSS: every stroke is `currentColor`, so one drawing
works in both the light and dark themes of the site.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .elements import Element, parse_circuit

__all__ = ["to_svg", "draw"]

# Element kinds laid out as a plain two-terminal box. `o` (op-amp) is
# three-terminal and handled separately; `m` (mutual inductance) couples
# two *elements* rather than two nodes and so is written above the
# drawing instead of placed in it; everything else falls back to a
# labelled rectangle, so an unrecognised kind still draws something
# honest.
TWO_TERMINAL = frozenset("rlcejs")

_UNIT = {"r": "Ω", "l": "H", "c": "F", "e": "V", "j": "A",
         "m": "H"}

# A value we are willing to append a unit to: a plain number with an
# optional SI-prefix letter. Anything else (vin, r_a, 5/s, 2*v_3) is a
# symbolic expression and is shown bare.
_NUMERIC = re.compile(
    r"^([+-]?[0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?)([a-zA-Zµμ]?)$")

# Prefix letters as the *input* shorthand defines them (si_prefix), and
# the subset used for *display*. These differ: input accepts K and both
# mu characters, output picks one spelling and sticks to it.
_IN_PREFIX = {"k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12,
              "P": 1e15, "m": 1e-3, "u": 1e-6, "µ": 1e-6, "μ": 1e-6,
              "n": 1e-9, "p": 1e-12, "f": 1e-15, "a": 1e-18}
_OUT_PREFIX = [(1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""),
               (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p"),
               (1e-15, "f")]


def _engineering(text: str) -> Optional[str]:
    """`1e-6` -> `1µ`, `1000` -> `1k`, `1'u` -> `1µ`. Returns None when
    the value is not a plain number, which is the signal to show it
    verbatim: symbolic values like `r_a` or `5/s` must never be
    reformatted."""
    m = _NUMERIC.match(text)
    if not m:
        return None
    mantissa, letter = m.group(1), m.group(2)
    if letter and letter not in _IN_PREFIX:
        return None
    try:
        num = float(mantissa) * (_IN_PREFIX[letter] if letter else 1.0)
    except (ValueError, OverflowError):
        return None
    if num == 0:
        return "0"
    factor, prefix = 1.0, ""
    for f, p in _OUT_PREFIX:
        if abs(num) >= f:
            factor, prefix = f, p
            break
    else:
        return "{0:g}".format(num)
    scaled = "{0:.4g}".format(num / factor)
    if "." in scaled:
        scaled = scaled.rstrip("0").rstrip(".")
    return scaled + prefix

# --- geometry -------------------------------------------------------
COL_W = 132        # horizontal distance between adjacent node columns
ROW_H = 150        # top row of nodes down to the ground rail
STACK_H = 78       # extra height per stacked parallel branch
OP_LANE_H = 78     # extra height per extra op-amp lane
MARGIN = 58
BODY = 46          # length of the symbol body itself, leads excluded
DOT_R = 3.4


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def _pretty(e: Element) -> str:
    """Label text for an element value: the SI-prefix quote is dropped
    (1'k -> 1k) and a unit appended when the value is a bare number
    rather than a symbol."""
    raw = e.value
    if raw is None:
        return ""
    val = raw.replace("'", "").strip()
    eng = _engineering(val)
    if eng is None:
        return val
    return eng + _UNIT.get(e.kind, "")


class _Canvas:
    """Collects SVG fragments and tracks the bounding box, so the
    viewBox is computed from what was actually drawn rather than
    predicted up front."""

    def __init__(self) -> None:
        self.parts: List[str] = []
        self.x0 = self.y0 = 1e9
        self.x1 = self.y1 = -1e9

    def _bound(self, *pts: Tuple[float, float]) -> None:
        for x, y in pts:
            self.x0, self.x1 = min(self.x0, x), max(self.x1, x)
            self.y0, self.y1 = min(self.y0, y), max(self.y1, y)

    def wire(self, x1: float, y1: float, x2: float, y2: float) -> None:
        if abs(x1 - x2) < 0.01 and abs(y1 - y2) < 0.01:
            return
        self._bound((x1, y1), (x2, y2))
        self.parts.append(
            '<line x1="{0:g}" y1="{1:g}" x2="{2:g}" y2="{3:g}"/>'
            .format(x1, y1, x2, y2))

    def dot(self, x: float, y: float) -> None:
        self._bound((x, y))
        self.parts.append(
            '<circle cx="{0:g}" cy="{1:g}" r="{2:g}" fill="currentColor" '
            'stroke="none"/>'.format(x, y, DOT_R))

    def text(self, x: float, y: float, s: str, anchor: str = "middle") -> None:
        if not s:
            return
        self._bound((x - 24, y - 12), (x + 24, y + 5))
        self.parts.append(
            '<text class="lbl" x="{0:g}" y="{1:g}" text-anchor="{2}">{3}</text>'
            .format(x, y, anchor, _esc(s)))

    def raw(self, svg: str, *corners: Tuple[float, float]) -> None:
        self._bound(*corners)
        self.parts.append(svg)


# --- symbol bodies --------------------------------------------------
# Each returns SVG drawn along the +x axis starting at (0,0), with the
# body centred on a segment of the given length. Keeping them in local
# coordinates means a vertical element is the same code plus a rotate()
# on the enclosing group.

def _body_r(length: float) -> str:
    lead = (length - BODY) / 2.0
    step, amp = BODY / 6.0, 9.0
    d = ["M0 0 L{0:g} 0".format(lead)]
    for i in range(6):
        d.append("L{0:g} {1:g}".format(lead + step * (i + 0.5),
                                       amp if i % 2 == 0 else -amp))
    d.append("L{0:g} 0 L{1:g} 0".format(lead + BODY, length))
    return '<path d="{0}"/>'.format(" ".join(d))


def _body_c(length: float) -> str:
    mid, gap, h = length / 2.0, 5.5, 13.0
    return ('<path d="M0 0 L{0:g} 0 M{1:g} 0 L{2:g} 0"/>'
            '<path d="M{0:g} {3:g} L{0:g} {4:g}"/>'
            '<path d="M{1:g} {3:g} L{1:g} {4:g}"/>'
            .format(mid - gap, mid + gap, length, -h, h))


def _body_l(length: float) -> str:
    lead = (length - BODY) / 2.0
    r = BODY / 8.0
    d = ["M0 0 L{0:g} 0".format(lead)]
    for _ in range(4):
        d.append("a{0:g} {0:g} 0 0 1 {1:g} 0".format(r, 2 * r))
    d.append("L{0:g} 0".format(length))
    return '<path d="{0}"/>'.format(" ".join(d))


def _body_e(length: float) -> str:
    """Independent or dependent voltage source: leads and the circle
    only. The + and - polarity marks are added afterwards by
    `_polarity`, in absolute coordinates -- drawn here they would be
    caught by the group's rotate() and a vertical source would end up
    with a minus sign standing on end."""
    mid, r = length / 2.0, 15.0
    return ('<path d="M0 0 L{0:g} 0 M{1:g} 0 L{2:g} 0"/>'
            '<circle cx="{3:g}" cy="0" r="{4:g}" fill="none"/>'
            .format(mid - r, mid + r, length, mid, r))


def _body_j(length: float) -> str:
    """Current source, arrow pointing n1 -> n2: the solver's positive
    i_<name> leaves n1 through the element (engine.add_current)."""
    mid, r = length / 2.0, 15.0
    return ('<path d="M0 0 L{0:g} 0 M{1:g} 0 L{2:g} 0"/>'
            '<circle cx="{3:g}" cy="0" r="{4:g}" fill="none"/>'
            '<path d="M{5:g} 0 L{6:g} 0"/>'
            '<path d="M{7:g} -4 L{6:g} 0 L{7:g} 4" fill="currentColor"/>'
            .format(mid - r, mid + r, length, mid, r,
                    mid - 9, mid + 9, mid + 3))


def _body_s(length: float) -> str:
    return '<path d="M0 0 L{0:g} 0"/>'.format(length)


def _body_box(length: float, letter: str) -> str:
    lead, h = (length - BODY) / 2.0, 26.0
    return ('<path d="M0 0 L{0:g} 0 M{1:g} 0 L{2:g} 0"/>'
            '<rect x="{0:g}" y="{3:g}" width="{4:g}" height="{5:g}" '
            'fill="none"/>'
            '<text class="lbl" x="{6:g}" y="4" text-anchor="middle">{7}</text>'
            .format(lead, lead + BODY, length, -h / 2, BODY, h,
                    lead + BODY / 2, _esc(letter)))


_BODIES = {"r": _body_r, "c": _body_c, "l": _body_l,
           "e": _body_e, "j": _body_j, "s": _body_s}


def _coupling_dot(cv: _Canvas, x1: float, y1: float, x2: float,
                  y2: float) -> None:
    """Polarity dot for a coupled inductor, at its n1 terminal.

    Which terminal gets the dot is not a choice: engine._stamp_l adds
    the coupling as +M*i_other with no orientation term, and the
    solver's positive current enters at n1 (engine.add_current). So
    current into n1 of one coil raises v(n1) - v(n2) of the other, which
    is precisely what the dot convention marks -- n1, on every coupled
    inductor, every time. A winding wound the other way is expressed by
    a negative M, not by moving the dot.

    The dot is offset to the side the value labels do not occupy: above
    a horizontal coil, left of a vertical one."""
    dx, dy = x2 - x1, y2 - y1
    span = (dx * dx + dy * dy) ** 0.5
    if span < BODY:
        return
    ux, uy = dx / span, dy / span
    along = max((span - BODY) / 2.0 - 6.0, 8.0)
    ox, oy = (0.0, -10.0) if abs(dx) > abs(dy) else (-10.0, 0.0)
    cv.dot(x1 + ux * along + ox, y1 + uy * along + oy)


def _polarity(cv: _Canvas, x1: float, y1: float, x2: float,
              y2: float) -> None:
    """Mark a voltage source + at the n1 end and - at the n2 end, which
    is the sign the solver uses: v(n1) - v(n2) = value (engine._stamp_e).

    Both marks are drawn in absolute screen coordinates rather than
    along the element's own axis, so the minus stays a horizontal bar
    whichever way the source is oriented."""
    dx, dy = x2 - x1, y2 - y1
    span = (dx * dx + dy * dy) ** 0.5
    if span < 1:
        return
    ux, uy = dx / span, dy / span          # n1 -> n2, unit length
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    off, arm = 7.0, 3.5
    px_, py = cx - ux * off, cy - uy * off     # + sits toward n1
    mx_, my_ = cx + ux * off, cy + uy * off    # - sits toward n2
    cv.raw('<path d="M{0:g} {1:g} L{2:g} {1:g} M{3:g} {4:g} L{3:g} {5:g}"/>'
           .format(px_ - arm, py, px_ + arm, px_, py - arm, py + arm),
           (px_ - arm, py - arm), (px_ + arm, py + arm))
    cv.raw('<path d="M{0:g} {1:g} L{2:g} {1:g}"/>'
           .format(mx_ - arm, my_, mx_ + arm),
           (mx_ - arm, my_), (mx_ + arm, my_))


def _draw_element(cv: _Canvas, e: Element, x1: float, y1: float,
                  x2: float, y2: float) -> Tuple[float, float]:
    """Draw `e` along the axis-aligned segment (x1,y1)-(x2,y2), oriented
    so that its n1 terminal is the (x1,y1) end. Returns the midpoint, so
    a later pass can tie two element bodies together (mutual
    inductance)."""
    vertical = abs(x2 - x1) < 0.5
    length = abs(y2 - y1) if vertical else abs(x2 - x1)
    maker = _BODIES.get(e.kind)
    body = maker(length) if maker else _body_box(length, e.kind.upper())

    # Labels are emitted outside the rotated group, in absolute
    # coordinates, so that a vertical element's text stays horizontal.
    if vertical:
        top, bot = min(y1, y2), max(y1, y2)
        if y1 < y2:
            tf = "translate({0:g},{1:g}) rotate(90)".format(x1, top)
        else:
            tf = "translate({0:g},{1:g}) rotate(-90)".format(x1, bot)
        cv.raw('<g transform="{0}">{1}</g>'.format(tf, body),
               (x1 - 22, top), (x1 + 22, bot))
        mx, my = x1, (top + bot) / 2.0
        cv.text(mx + 17, my - 3, e.name, "start")
        cv.text(mx + 17, my + 12, _pretty(e), "start")
    else:
        left, right = min(x1, x2), max(x1, x2)
        if x1 < x2:
            tf = "translate({0:g},{1:g})".format(left, y1)
        else:
            tf = "translate({0:g},{1:g}) rotate(180)".format(right, y1)
        cv.raw('<g transform="{0}">{1}</g>'.format(tf, body),
               (left, y1 - 22), (right, y1 + 22))
        mx, my = (x1 + x2) / 2.0, y1
        cv.text(mx, my - 25, e.name)
        cv.text(mx, my - 11, _pretty(e))
    if e.kind == "e":
        _polarity(cv, x1, y1, x2, y2)
    return mx, my


# --- layout ---------------------------------------------------------

def _node_order(elements: List[Element]) -> List[str]:
    """Left-to-right ordering of the non-ground nodes: a depth-first
    walk over the element graph, started from each node in the order it
    first appears in the description. DFS rather than BFS because a
    chain of elements must come out as a chain -- BFS distance ties
    would collapse two branches into one column."""
    adj: Dict[str, List[str]] = {}
    seen: List[str] = []

    def note(n: str) -> None:
        if n != "0" and n not in adj:
            adj[n] = []
            seen.append(n)

    for e in elements:
        if e.kind in TWO_TERMINAL:
            note(e.n1)
            note(e.n2)
        elif e.kind == "o":
            for n in e.fields[:3]:
                note(n)
        elif e.kind != "m":
            note(e.n1)
            note(e.n2)

    def link(a: str, b: str) -> None:
        if a != "0" and b != "0" and a != b:
            adj[a].append(b)
            adj[b].append(a)

    for e in elements:
        if e.kind == "m":
            continue
        if e.kind == "o":
            # An op-amp is not a two-terminal edge, but its inverting
            # input and its output do have to end up adjacent, or the
            # output node gets stranded in its own component.
            link(e.fields[1], e.fields[2])
        else:
            link(e.n1, e.n2)

    order: List[str] = []
    visited = set()
    for start in seen:
        if start in visited:
            continue
        stack = [start]
        while stack:
            n = stack.pop()
            if n in visited:
                continue
            visited.add(n)
            order.append(n)
            for m in reversed(adj[n]):
                if m not in visited:
                    stack.append(m)
    return order


class _Layout:
    """Column assignment and the resulting pixel geometry."""

    def __init__(self, elements: List[Element]) -> None:
        self.elements = elements
        self.grounded: List[Element] = []
        self.spanning: List[Element] = []
        self.opamps: List[Element] = []
        self.mutuals: List[Element] = []

        for e in elements:
            if e.kind == "m":
                self.mutuals.append(e)
            elif e.kind == "o":
                self.opamps.append(e)
            elif e.n1 == e.n2:
                continue          # degenerate self-loop: nothing to draw
            elif e.n1 == "0" or e.n2 == "0":
                self.grounded.append(e)
            else:
                self.spanning.append(e)

        self.node_col: Dict[str, int] = {}
        self.elem_col: Dict[str, int] = {}      # grounded elements
        self.level: Dict[str, int] = {}         # spanning elements
        self.op_lane: Dict[str, int] = {}       # op-amps
        self._assign()

    def _assign(self) -> None:
        by_node: Dict[str, List[Element]] = {}
        for e in self.grounded:
            n = e.n2 if e.n1 == "0" else e.n1
            by_node.setdefault(n, []).append(e)

        col = 0
        stubs: List[Tuple[int, int, int]] = []
        for n in _node_order(self.elements):
            self.node_col[n] = col
            col += 1
            # The first element to ground hangs straight down from the
            # node; any further ones are in parallel with it and need
            # their own column, reached by a stub along the top row.
            for i, e in enumerate(by_node.get(n, [])):
                if i == 0:
                    self.elem_col[e.name] = self.node_col[n]
                else:
                    self.elem_col[e.name] = col
                    stubs.append((self.node_col[n], col, 0))
                    col += 1
        self.cols = max(col, 1)

        # Each element between two live nodes occupies the interval
        # between their columns on whichever row it is drawn. Two
        # intervals that share more than an endpoint cannot both sit on
        # the node row, so this colours the interval graph greedily from
        # the left and stacks the losers above, with risers back down at
        # each end.
        #
        # Bumping only exact duplicates (which is all "in parallel"
        # means) is not enough: in a bridge the element from node 1 to
        # node 3 spans *over* node 2, and would otherwise be drawn
        # straight through the two elements either side of it. Parallel
        # elements are just the special case where the two intervals are
        # identical, so one rule covers both. Stubs out to a parallel
        # ground column are pre-placed on row 0 for the same reason.
        spans = [(min(self.node_col[e.n1], self.node_col[e.n2]),
                  max(self.node_col[e.n1], self.node_col[e.n2]), e)
                 for e in self.spanning]
        spans.sort(key=lambda s: (s[0], s[1]))
        placed: List[Tuple[int, int, int]] = list(stubs)
        for lo, hi, e in spans:
            lvl = 0
            while any(l == lvl and min(hi, h) > max(lo, o)
                      for o, h, l in placed):
                lvl += 1
            self.level[e.name] = lvl
            placed.append((lo, hi, lvl))
        self.max_level = max(self.level.values(), default=0)

        # Op-amps all sit in one horizontal band, so two whose
        # input-to-output columns overlap would be drawn through each
        # other. Identical colouring to the rows above, except the
        # colours become lanes *down* the band. A cascade keeps lane 0
        # throughout, since each stage owns its own columns.
        ops = []
        for e in self.opamps:
            a = self.node_col.get(e.fields[1])
            b = self.node_col.get(e.fields[2])
            if a is not None and b is not None:
                ops.append((min(a, b), max(a, b), e))
        ops.sort(key=lambda s: (s[0], s[1]))
        taken: List[Tuple[int, int, int]] = []
        for lo, hi, e in ops:
            lane = 0
            while any(l == lane and min(hi, h) > max(lo, o)
                      for o, h, l in taken):
                lane += 1
            self.op_lane[e.name] = lane
            taken.append((lo, hi, lane))
        self.max_op_lane = max(self.op_lane.values(), default=0)

    # pixel helpers
    def px(self, col: int) -> float:
        return MARGIN + col * COL_W

    @property
    def y_top(self) -> float:
        return MARGIN + self.max_level * STACK_H

    @property
    def y_bot(self) -> float:
        return self.y_top + ROW_H + self.max_op_lane * OP_LANE_H


# --- rendering ------------------------------------------------------

def _draw_opamp(cv: _Canvas, lay: _Layout, e: Element) -> Optional[float]:
    """Ideal op-amp (nullor): a triangle between the inverting input's
    column and the output's column, sitting below the top row.

    The inverting input is drawn as the *upper* pin and the
    non-inverting as the lower one -- the opposite of the usual
    convention, but it is what keeps the two input wires from crossing
    in the common case, where the inverting input comes down from the
    node row and the non-inverting one goes to ground.

    Returns the x at which its non-inverting input meets the ground
    rail, or None if that input is not grounded -- the caller needs it
    to size the rail, or the wire drawn here would dangle."""
    n_plus, n_minus, n_out = e.fields[0], e.fields[1], e.fields[2]
    x_in = lay.px(lay.node_col[n_minus]) if n_minus in lay.node_col \
        else lay.px(0)
    x_out = lay.px(lay.node_col[n_out]) if n_out in lay.node_col \
        else x_in + COL_W

    lane = lay.op_lane.get(e.name, 0)
    mid = lay.y_top + ROW_H / 2.0 + lane * OP_LANE_H
    # The triangle is a fixed equilateral symbol, centred in the gap
    # between the input and output columns. Widening it to span whatever
    # gap it happens to sit in would be the easy way to make the wires
    # meet, but it distorts the symbol; the leads stretch instead.
    h = 58.0
    w = h * 3 ** 0.5 / 2.0
    tx = max((x_in + x_out) / 2.0 - w / 2.0, x_in + 26)
    y_minus, y_plus = mid - h / 4.0, mid + h / 4.0

    cv.raw('<path d="M{0:g} {1:g} L{0:g} {2:g} L{3:g} {4:g} Z" fill="none"/>'
           .format(tx, mid - h / 2, mid + h / 2, tx + w, mid),
           (tx, mid - h / 2), (tx + w, mid + h / 2))
    cv.text(tx + 13, y_minus + 5, "−", "middle")
    cv.text(tx + 13, y_plus + 5, "+", "middle")
    cv.text(tx + w / 2, mid - h / 2 - 8, e.name)

    # inverting input: straight down from its node, then in
    cv.wire(x_in, lay.y_top, x_in, y_minus)
    cv.wire(x_in, y_minus, tx, y_minus)
    # When several op-amps hang off one input node they share that
    # vertical wire, so the branch to this one is a T-junction and needs
    # a dot -- but only if another op-amp continues on past it.
    if any(o.name != e.name and o.fields[1] == n_minus
           and lay.op_lane.get(o.name, 0) > lane for o in lay.opamps):
        cv.dot(x_in, y_minus)
    # non-inverting input: out to the left, then down to the rail (or up
    # to its own node row if it is not grounded)
    x_p = x_in - 30 - lane * 16
    cv.wire(tx, y_plus, x_p, y_plus)
    if n_plus == "0":
        cv.wire(x_p, y_plus, x_p, lay.y_bot)
        grounded_at: Optional[float] = x_p
    else:
        grounded_at = None
    if n_plus != "0":
        xp_node = lay.px(lay.node_col[n_plus])
        cv.wire(x_p, y_plus, x_p, lay.y_top + 12)
        cv.wire(x_p, lay.y_top + 12, xp_node, lay.y_top + 12)
        cv.wire(xp_node, lay.y_top + 12, xp_node, lay.y_top)
    # output: up to its node on the top row
    cv.wire(tx + w, mid, x_out, mid)
    cv.wire(x_out, mid, x_out, lay.y_top)
    return grounded_at


def _render(elements: List[Element]) -> str:
    lay = _Layout(elements)
    cv = _Canvas()
    y_top, y_bot = lay.y_top, lay.y_bot
    # Oriented segment per element, n1 end first: the coupling dots need
    # to know which way round each coil was actually drawn.
    segs: Dict[str, Tuple[float, float, float, float]] = {}

    # 1. elements between two non-ground nodes, along the top row
    for e in lay.spanning:
        lvl = lay.level[e.name]
        y = y_top - lvl * STACK_H
        xa, xb = lay.px(lay.node_col[e.n1]), lay.px(lay.node_col[e.n2])
        if lvl:
            # a stacked parallel branch: risers at each end back down to
            # the row the node actually lives on
            cv.wire(xa, y_top, xa, y)
            cv.wire(xb, y_top, xb, y)
        _draw_element(cv, e, xa, y, xb, y)
        segs[e.name] = (xa, y, xb, y)

    # 2. elements with one terminal on ground, hanging down to the rail
    ground_x: List[float] = []
    for e in lay.grounded:
        n = e.n2 if e.n1 == "0" else e.n1
        col_e, col_n = lay.elem_col[e.name], lay.node_col[n]
        x, xn = lay.px(col_e), lay.px(col_n)
        if col_e != col_n:
            cv.wire(xn, y_top, x, y_top)   # stub to a parallel column
        # keep n1 at the end the element was declared from
        if e.n1 == "0":
            segs[e.name] = (x, y_bot, x, y_top)
        else:
            segs[e.name] = (x, y_top, x, y_bot)
        _draw_element(cv, e, *segs[e.name])
        ground_x.append(x)

    # 3. op-amps, before the rail is sized: a grounded non-inverting
    #    input is one more thing the rail has to reach.
    for e in lay.opamps:
        gx = _draw_opamp(cv, lay, e)
        if gx is not None:
            ground_x.append(gx)

    # 4. the ground rail, plus a symbol at its left end
    if ground_x:
        gx0, gx1 = min(ground_x), max(ground_x)
        cv.wire(gx0, y_bot, gx1, y_bot)
        for x in sorted(set(ground_x)):
            if gx0 < x < gx1:
                cv.dot(x, y_bot)
        cv.wire(gx0, y_bot, gx0, y_bot + 12)
        for i, half in enumerate((11.0, 7.0, 3.0)):
            yy = y_bot + 12 + i * 4
            cv.wire(gx0 - half, yy, gx0 + half, yy)
        # Name the reference node, same as every other node is named --
        # "0" is a node in the description like any other, and readers
        # tracing v_2 back to its reference need to see it.
        cv.text(gx0 + 16, y_bot + 21, "0", "start")
        cv.raw("", (gx0 - 14, y_bot + 26))

    # 5. junction dots on the top row wherever three or more things meet
    touching: Dict[str, int] = {}
    for e in elements:
        terms = e.fields[:3] if e.kind == "o" else (
            [] if e.kind == "m" else [e.n1, e.n2])
        for n in terms:
            touching[n] = touching.get(n, 0) + 1
    for n, count in touching.items():
        if n != "0" and count >= 3 and n in lay.node_col:
            cv.dot(lay.px(lay.node_col[n]), y_top)

    # 6. node names, tucked just above the row
    for n, col in lay.node_col.items():
        cv.text(lay.px(col) + 6, y_top - 6, n, "start")

    # 7. mutual inductance, written above the drawing rather than drawn
    #    into it: `m` couples two *elements*, not two nodes, so there is
    #    no honest place to put it on the circuit itself -- a dashed tie
    #    between the two coils just reads as another wire.
    #    The polarity, though, does belong on the circuit: a dot at each
    #    coupled coil's n1 terminal, which is what the solver's sign
    #    convention means in schematic notation (see `_coupling_dot`).
    for e in lay.mutuals:
        for coil in (e.n1, e.n2):
            if coil in segs:
                _coupling_dot(cv, *segs[coil])
    captions = ["{0} = {1}  (couples {2} and {3})".format(
        e.name, _pretty(e), e.n1, e.n2) for e in lay.mutuals]
    if captions:
        cx, cy = cv.x0, cv.y0 - 14
        for i, line in enumerate(reversed(captions)):
            cv.text(cx, cy - i * 17, line, "start")

    x0, y0 = cv.x0 - 26, cv.y0 - 26
    w, h = (cv.x1 - cv.x0) + 52, (cv.y1 - cv.y0) + 52
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'viewBox="{0:g} {1:g} {2:g} {3:g}" width="{2:g}" height="{3:g}" '
        'fill="none" stroke="currentColor" stroke-width="1.7" '
        'stroke-linecap="round" stroke-linejoin="round" '
        'class="symbulator-schematic">'
        '<style>.symbulator-schematic .lbl{{font:13px/1 ui-sans-serif,'
        'system-ui,sans-serif;fill:currentColor;stroke:none}}</style>'
        '{4}</svg>'
    ).format(x0, y0, w, h, "".join(cv.parts))


def to_svg(desc: str) -> str:
    """Render a Symbulator circuit description as a standalone SVG
    string.

    >>> "svg" in to_svg("e1,1,0,5:r1,1,2,1'k:r2,2,0,1'k")
    True
    """
    return _render(parse_circuit(desc, expand_si=False))


def draw(desc: str):
    """Same as `to_svg`, wrapped so a notebook or the browser build can
    display it directly."""
    svg = to_svg(desc)
    try:
        from IPython.display import SVG      # type: ignore
        return SVG(svg)
    except ImportError:
        return svg


# LIMITATIONS (prototype)
# -----------------------
# * A bridge draws correctly -- the element spanning over an
#   intermediate node is lifted to its own row -- but as a ladder with a
#   jumper over the top, not as the diamond most textbooks print.
#   Recognising a bridge as a diamond means special-casing the topology,
#   which the interval stacking deliberately avoids.
# * A coupled inductor carries one polarity dot, so an inductor coupled
#   to two others with opposite signs cannot be drawn faithfully -- the
#   dot convention itself has no notation for it. The caption still
#   shows each M with its sign.
# * A non-grounded op-amp `+` input is routed, but may cross other wires.
# * Two-port blocks (z/y/h/g/a/b) and the transformer `t` draw as a
#   labelled box, without their port parameters.
