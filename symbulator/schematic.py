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


# A float literal long enough to be floating-point dust rather than a
# number anyone typed: eight or more significant digits.
_LONG_FLOAT = re.compile(r"\d*\.\d{7,}(?:[eE][+-]?\d+)?")

# `30*pi/180` is how an angle in degrees is written where the solver
# needs radians; the schematic shows it back as the degrees it means.
_DEG_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\*\s*pi\s*/\s*180(?![\d.])")

# A value longer than this is not lettered at the element -- the
# element keeps its name and the value moves to a caption line below
# the drawing (same block the mutual inductances already use).
CAPTION_LEN = 16


def _round_long_floats(text: str) -> str:
    """`173.20508075688772` -> `173.21`. Only rewrites literals long
    enough that no one wrote them by hand -- they are the residue of an
    expansion (a phasor turned rectangular, a computed coefficient) and
    carry no five-decimal information a schematic reader could use."""
    def shorten(m):
        try:
            return "{0:.5g}".format(float(m.group(0)))
        except (ValueError, OverflowError):
            return m.group(0)
    return _LONG_FLOAT.sub(shorten, text)


def _strip_outer_parens(text: str) -> str:
    """Drop redundant enclosing parentheses: `((110∠0°))` -> `110∠0°`.
    Only when the outermost pair actually matches around the whole
    string, so `(a)+(b)` keeps its parens."""
    while len(text) >= 2 and text[0] == "(" and text[-1] == ")":
        depth = 0
        for i, ch in enumerate(text):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i < len(text) - 1:
                    return text
        text = text[1:-1].strip()
    return text


def _pretty(e: Element) -> str:
    """Label text for an element value: shown the way the reader typed
    it (raw_fields survives shorthand expansion -- a phasor stays
    `110∠0°` instead of its 17-digit rectangular expansion), with the
    SI-prefix quote dropped (1'k -> 1k), redundant outer parentheses
    removed, long float literals rounded, and a unit appended when the
    value is a bare number rather than a symbol."""
    raw = e.value
    if raw is None:
        return ""
    if e.raw_fields and len(e.raw_fields) > 2:
        raw = e.raw_fields[2]
    val = raw.replace("'", "").strip()
    val = _strip_outer_parens(val)
    val = _round_long_floats(val)
    val = _DEG_RE.sub("\\1\u00b0", val)
    # The parallel-impedance shortcut back in the reader's own
    # notation: `[a,b]` was rewritten to `pr(a,b)` before the fields
    # were split (raw_fields cannot preserve it -- the bracket's inner
    # comma makes the typed text split differently), so it is restored
    # here, innermost first when they nest.
    while "pr(" in val:
        swapped = re.sub(r"pr\(([^()]*)\)", r"[\1]", val)
        if swapped == val:
            break
        val = swapped
    eng = _engineering(val)
    if eng is None:
        return val
    return eng + _UNIT.get(e.kind, "")


HOP_R = 5.0    # radius of the semicircular hop where one wire crosses another
_EPS = 0.5


def _hop_path(a: float, b: float, c: float, pts: List[float],
              horizontal: bool) -> str:
    """One wire from a to b (at cross-coordinate c) with a semicircular
    hop at each of `pts` -- the standard notation for a crossing that
    is not a connection. Plain wires stay `<line>` elements."""
    # A hop too close to the wire's end (or to the previous hop) has no
    # room for its arc; drop it rather than draw a mangled bump.
    usable: List[float] = []
    for p in pts:
        if p - HOP_R < a + 1 or p + HOP_R > b - 1:
            continue
        if usable and p - HOP_R < usable[-1] + HOP_R + 1:
            continue
        usable.append(p)
    if not usable:
        if horizontal:
            return ('<line x1="{0:g}" y1="{1:g}" x2="{2:g}" y2="{1:g}"/>'
                    .format(a, c, b))
        return ('<line x1="{0:g}" y1="{1:g}" x2="{0:g}" y2="{2:g}"/>'
                .format(c, a, b))
    d: List[str] = []
    if horizontal:
        d.append("M{0:g} {1:g}".format(a, c))
        for p in usable:
            d.append("L{0:g} {1:g}".format(p - HOP_R, c))
            d.append("A{0:g} {0:g} 0 0 1 {1:g} {2:g}".format(
                HOP_R, p + HOP_R, c))
        d.append("L{0:g} {1:g}".format(b, c))
    else:
        d.append("M{0:g} {1:g}".format(c, a))
        for p in usable:
            d.append("L{0:g} {1:g}".format(c, p - HOP_R))
            d.append("A{0:g} {0:g} 0 0 0 {1:g} {2:g}".format(
                HOP_R, c, p + HOP_R))
        d.append("L{0:g} {1:g}".format(c, b))
    return '<path d="{0}"/>'.format(" ".join(d))


class _Canvas:
    """Collects SVG fragments and tracks the bounding box, so the
    viewBox is computed from what was actually drawn rather than
    predicted up front.

    Wires and junction dots are *collected* rather than emitted: at
    flush time every horizontal-vertical crossing that is interior to
    both wires -- a place two unconnected wires pass each other -- is
    drawn as a small semicircular hop on the horizontal wire, the
    standard no-connection notation, and every endpoint that lands on
    the interior of a perpendicular wire gets a junction dot, so a
    T-connection and a crossing can never be confused."""

    def __init__(self) -> None:
        self.parts: List[str] = []
        self.x0 = self.y0 = 1e9
        self.x1 = self.y1 = -1e9
        self.wires: List[Tuple[float, float, float, float]] = []
        # Element segments: the axis line an element body sits on, kept
        # so a wire crossing an element's *lead* still gets its hop.
        # (Crossing the body itself is a layout failure the column and
        # level assignment is responsible for preventing.)
        self.esegs: List[Tuple[float, float, float, float]] = []
        # Solid regions no wire may enter (op-amp triangle bodies):
        # nothing routes around them at draw time -- the layout is
        # responsible for never sending a wire there -- but keeping
        # them lets a verification harness prove that it didn't.
        self.obstacles: List[Tuple[float, float, float, float]] = []
        self.dots: List[Tuple[float, float]] = []

    def _bound(self, *pts: Tuple[float, float]) -> None:
        for x, y in pts:
            self.x0, self.x1 = min(self.x0, x), max(self.x1, x)
            self.y0, self.y1 = min(self.y0, y), max(self.y1, y)

    def wire(self, x1: float, y1: float, x2: float, y2: float) -> None:
        if abs(x1 - x2) < 0.01 and abs(y1 - y2) < 0.01:
            return
        self._bound((x1, y1), (x2, y2))
        self.wires.append((min(x1, x2), min(y1, y2),
                           max(x1, x2), max(y1, y2)))

    def eseg(self, x1: float, y1: float, x2: float, y2: float,
             half: float = 23.0) -> None:
        """Register an element's axis segment. `half` is the body's
        half-length along the axis, centred on the midpoint -- the zone
        a wire must never cross (the leads either side of it may be
        crossed, with a hop)."""
        self.esegs.append((min(x1, x2), min(y1, y2),
                           max(x1, x2), max(y1, y2), half))

    def obstacle(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.obstacles.append((x0, y0, x1, y1))

    def dot(self, x: float, y: float) -> None:
        self._bound((x, y))
        self.dots.append((x, y))

    def _flush_wires(self) -> None:
        """Emit the collected wires: merged where collinear runs
        overlap, with a hop wherever one wire crosses another (or an
        element's lead) without connecting, and a junction dot wherever
        a wire or element endpoint tees into a passing wire."""
        hor = [w for w in self.wires if abs(w[1] - w[3]) < 0.01]
        ver = [w for w in self.wires if abs(w[0] - w[2]) < 0.01]
        eh = [s for s in self.esegs if abs(s[1] - s[3]) < 0.01]
        ev = [s for s in self.esegs if abs(s[0] - s[2]) < 0.01]

        def merge(runs, key_i, lo_i, hi_i):
            """Overlapping collinear runs (double-drawn risers) as one."""
            merged: List[List[float]] = []
            for r in sorted(runs, key=lambda r: (r[key_i], r[lo_i])):
                for m in merged:
                    if abs(m[key_i] - r[key_i]) < 0.01 \
                            and r[lo_i] <= m[hi_i] + 0.01 \
                            and m[lo_i] <= r[hi_i] + 0.01:
                        m[lo_i] = min(m[lo_i], r[lo_i])
                        m[hi_i] = max(m[hi_i], r[hi_i])
                        break
                else:
                    merged.append(list(r))
            return [tuple(m) for m in merged]

        hor = merge(hor, 1, 0, 2)
        ver = merge(ver, 0, 1, 3)

        # Junction dots at T-joints: an endpoint on the interior of a
        # perpendicular wire is a connection, and drawing its dot is
        # what lets the hops below carry the opposite meaning.
        for xa, ya, xb, yb in [w[:4] for w in hor] + [s[:4] for s in eh]:
            for x, y1, _, y2 in ver:
                for px_ in (xa, xb):
                    if abs(px_ - x) < _EPS and y1 + _EPS < ya < y2 - _EPS:
                        self.dot(px_, ya)
        for x, ya, _, yb in [w[:4] for w in ver] + [s[:4] for s in ev]:
            for x1, y, x2, _ in hor:
                for py in (ya, yb):
                    if abs(py - y) < _EPS and x1 + _EPS < x < x2 - _EPS:
                        self.dot(x, py)

        # Hops: the horizontal wire jumps over vertical wires and
        # vertical element leads; a vertical wire only ever needs to
        # jump where a horizontal *element* is in its way, since
        # wire-wire crossings already got their hop on the horizontal.
        for x1, y, x2, _y in hor:
            pts = sorted(
                x for x, ya, _, yb in [w[:4] for w in ver]
                + [s[:4] for s in ev]
                if x1 + _EPS < x < x2 - _EPS and ya + _EPS < y < yb - _EPS)
            self.parts.append(_hop_path(x1, x2, y, pts, horizontal=True))
        for x, y1, _x, y2 in ver:
            pts = sorted(
                y for xa, y, xb, _ in [s[:4] for s in eh]
                if y1 + _EPS < y < y2 - _EPS and xa + _EPS < x < xb - _EPS)
            self.parts.append(_hop_path(y1, y2, x, pts, horizontal=False))

        seen = set()
        for x, y in self.dots:
            key = (round(x), round(y))
            if key not in seen:
                seen.add(key)
                self.parts.append(
                    '<circle cx="{0:g}" cy="{1:g}" r="{2:g}" '
                    'fill="currentColor" stroke="none"/>'
                    .format(x, y, DOT_R))

    def flush(self) -> None:
        self._flush_wires()

    def text(self, x: float, y: float, s: str, anchor: str = "middle") -> None:
        if not s:
            return
        # Bound by an estimate of the rendered width (13px UI font,
        # ~7.2px average advance), so a long label widens the viewBox
        # instead of being clipped at its edge.
        w = len(s) * 7.2
        if anchor == "middle":
            x0, x1 = x - w / 2.0, x + w / 2.0
        elif anchor == "end":
            x0, x1 = x - w, x
        else:
            x0, x1 = x, x + w
        self._bound((x0, y - 12), (x1, y + 4))
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
    cv.eseg(x1, y1, x2, y2,
            half=15.0 if e.kind in ("e", "j") else
            0.0 if e.kind == "s" else 23.0)

    # Labels are emitted outside the rotated group, in absolute
    # coordinates, so that a vertical element's text stays horizontal.
    # A source's circle (r = 15) is taller and wider than the other
    # bodies, so its labels sit further out -- and a horizontal source
    # puts the value *below* the circle, where a resistor-height offset
    # would run the text straight through the stroke.
    round_body = e.kind in ("e", "j")
    val = _pretty(e)
    if len(val) > CAPTION_LEN:
        # Too long to letter at the element: the name stays, the value
        # goes to the caption block below the drawing (see _render).
        val = ""
    if vertical:
        top, bot = min(y1, y2), max(y1, y2)
        if y1 < y2:
            tf = "translate({0:g},{1:g}) rotate(90)".format(x1, top)
        else:
            tf = "translate({0:g},{1:g}) rotate(-90)".format(x1, bot)
        cv.raw('<g transform="{0}">{1}</g>'.format(tf, body),
               (x1 - 22, top), (x1 + 22, bot))
        mx, my = x1, (top + bot) / 2.0
        dx = 20 if round_body else 17
        cv.text(mx + dx, my - 3, e.name, "start")
        cv.text(mx + dx, my + 12, val, "start")
    else:
        left, right = min(x1, x2), max(x1, x2)
        if x1 < x2:
            tf = "translate({0:g},{1:g})".format(left, y1)
        else:
            tf = "translate({0:g},{1:g}) rotate(180)".format(right, y1)
        cv.raw('<g transform="{0}">{1}</g>'.format(tf, body),
               (left, y1 - 22), (right, y1 + 22))
        mx, my = (x1 + x2) / 2.0, y1
        if e.kind == "s" and length > COL_W * 1.5:
            # A long short is a plain wire whose midpoint is exactly
            # where another element's riser tends to cross it (shorts
            # jumper over things by nature); label it off-centre.
            mx = min(x1, x2) + length / 4.0
        if round_body:
            cv.text(mx, my - 22, e.name)
            cv.text(mx, my + 28, val)
        else:
            cv.text(mx, my - 25, e.name)
            if len(val) * 7.2 > 70:
                # A long value centred above the body would run into
                # the neighbouring node's name; below the wire is open.
                cv.text(mx, my + 20, val)
            else:
                cv.text(mx, my - 11, val)
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

    # Op-amp links first: an op-amp's inverting input and output are not
    # a two-terminal edge, but they do have to end up adjacent -- and
    # walking that link *before* any resistor edge is what makes a
    # cascade come out left to right. An adder's skip resistor (input
    # straight to the second stage's summing node) is declared early and
    # would otherwise drag the far output node into an early column,
    # leaving the first op-amp pointing backwards through its own
    # output wire.
    for e in elements:
        if e.kind == "o":
            link(_op_up(e), e.fields[2])
    # A weaker link second: non-inverting input to inverting input. For
    # a non-inverting stage the feedback divider hangs off n- and often
    # touches nothing else, so without this the only route to n- is
    # *through* the output node and the stage comes out backwards. n+
    # is usually ground, where link() is a no-op.
    for e in elements:
        if e.kind == "o":
            link(e.fields[0], e.fields[1])
    for e in elements:
        if e.kind not in ("m", "o"):
            link(e.n1, e.n2)

    # An op-amp's output node must land to the *right* of its inverting
    # input, or the triangle is drawn backwards with its output wire
    # retracing through the body. The link edges above make the two
    # adjacent, but another element (an adder's skip resistor, a shared
    # feedback network) can still hand the output node to the walk
    # early -- so an output node whose inverting input has not been
    # placed yet is deferred rather than visited. The forced pop when
    # the stack runs dry keeps a pathological circuit (an output node
    # that is the only path to its own input) from deadlocking; it just
    # falls back to the old order there.
    inv_input_of: Dict[str, str] = {}
    for e in elements:
        if e.kind == "o":
            inv_input_of.setdefault(e.fields[2], _op_up(e))

    order: List[str] = []
    visited = set()
    for start in seen:
        if start in visited:
            continue
        stack = [start]
        deferred: List[str] = []
        while stack or deferred:
            if not stack:
                stack.append(deferred.pop(0))
                forced = True
            else:
                forced = False
            n = stack.pop()
            if n in visited:
                continue
            minus = inv_input_of.get(n)
            if not forced and minus is not None and minus not in visited \
                    and minus in adj:
                deferred.append(n)
                continue
            visited.add(n)
            order.append(n)
            for m in reversed(adj[n]):
                if m not in visited:
                    stack.append(m)
    return order


def _ground_node(e: Element) -> str:
    """The non-ground terminal of a grounded two-terminal element."""
    return e.n2 if e.n1 == "0" else e.n1


def _op_up(e: Element) -> str:
    """The op-amp input drawn wired to the node row: the inverting
    input normally, but the non-inverting one when the inverting input
    is ground -- `o,1,0,o` is written that way round, and treating "0"
    as a column would run the input riser through whatever hangs on
    the leftmost column."""
    return e.fields[1] if e.fields[1] != "0" else e.fields[0]


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

        # A non-inverting stage's driving source -- a grounded e/j that
        # is the *only* thing on the op-amp's lower input -- is drawn in
        # the input drop itself, under the triangle, the way a textbook
        # draws it. Giving that node a top-row column of its own would
        # push the source out to the edge of the drawing and route its
        # wire across everything in between.
        self.op_src: Dict[str, Element] = {}
        self.captured: set = set()
        usage: Dict[str, List[Element]] = {}
        for e in elements:
            if e.kind == "m":
                continue
            terms = e.fields[:3] if e.kind == "o" else [e.n1, e.n2]
            for n in set(terms):
                if n != "0":
                    usage.setdefault(n, []).append(e)
        for op in self.opamps:
            # The input routed downward: n+ normally; when the pins are
            # flipped because n- is ground (see _op_up), the downward
            # input *is* ground and there is nothing to capture.
            dn = op.fields[0] if op.fields[1] != "0" else "0"
            if dn == "0" or dn == _op_up(op):
                continue
            users = usage.get(dn, [])
            if len(users) != 2 or op not in users:
                continue
            src = next((u for u in users
                        if u.kind in ("e", "j") and "0" in (u.n1, u.n2)),
                       None)
            if src is not None and src in self.grounded:
                self.op_src[op.name] = src
                self.captured.add(dn)
                self.grounded.remove(src)

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

        order = [n for n in _node_order(self.elements)
                 if n not in self.captured]
        idx = {n: i for i, n in enumerate(order)}

        # The columns an op-amp occupies, in node-order index space. A
        # grounded element hanging inside one of these spans would be
        # drawn straight through the triangle or its wires -- the band
        # between the node row and the rail is exactly where the op-amp
        # sits -- so such elements are bumped out to a column of their
        # own: before the span when they hang off the inverting-input
        # end (a driving source belongs on the left), after it
        # otherwise (a load belongs on the right).
        spans_idx: List[Tuple[int, int]] = []
        for e in self.opamps:
            a, b = idx.get(_op_up(e)), idx.get(e.fields[2])
            if a is not None and b is not None:
                spans_idx.append((min(a, b), max(a, b)))

        def span_of(i: int) -> Optional[Tuple[int, int]]:
            for lo, hi in spans_idx:
                if lo <= i <= hi:
                    return (lo, hi)
            return None

        def bump_target(i: int) -> Tuple[str, int]:
            """Where a grounded element on node index `i` (inside a
            span) gets its own column: ("L", j) = just before node j,
            ("R", j) = just after node j -- walked outward until the
            insertion gap is inside no span at all (cascades chain
            spans end to end)."""
            lo, hi = span_of(i)
            if i == lo:
                j, moved = lo, True
                while moved:
                    moved = False
                    for lo2, hi2 in spans_idx:
                        if lo2 < j <= hi2:
                            j, moved = lo2, True
                return ("L", j)
            j, moved = hi, True
            while moved:
                moved = False
                for lo2, hi2 in spans_idx:
                    if lo2 <= j < hi2:
                        j, moved = hi2, True
            return ("R", j)

        pre: Dict[int, List[Element]] = {}
        post: Dict[int, List[Element]] = {}
        at_node: List[Tuple[str, Element]] = []
        extra: Dict[int, List[Element]] = {}
        for n, elems in by_node.items():
            i = idx.get(n)
            if i is None:
                continue
            if span_of(i) is not None:
                side, j = bump_target(i)
                for e in elems:
                    (pre if side == "L" else post).setdefault(j, []).append(e)
            else:
                # The first element to ground hangs straight down from
                # the node; any further ones are in parallel with it and
                # need their own column, reached by a stub along the top
                # row.
                at_node.append((n, elems[0]))
                for e in elems[1:]:
                    extra.setdefault(i, []).append(e)

        col = 0
        own_col: List[Tuple[str, Element]] = []   # (node, elem) pairs
        for i, n in enumerate(order):
            for e in pre.get(i, []):
                self.elem_col[e.name] = col
                own_col.append((_ground_node(e), e))
                col += 1
            self.node_col[n] = col
            col += 1
            for e in extra.get(i, []):
                self.elem_col[e.name] = col
                own_col.append((_ground_node(e), e))
                col += 1
            for e in post.get(i, []):
                self.elem_col[e.name] = col
                own_col.append((_ground_node(e), e))
                col += 1
        self.cols = max(col, 1)

        for n, e in at_node:
            self.elem_col[e.name] = self.node_col[n]

        stubs: List[Tuple[int, int, int]] = []
        for n, e in own_col:
            a, b = self.node_col[n], self.elem_col[e.name]
            stubs.append((min(a, b), max(a, b), 0))

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
        # Narrow before wide: an interval nested inside another must end
        # up *below* it, so the outer element's risers drop past the
        # inner one's endpoints (a shared node -- a junction) instead of
        # the inner element's risers slicing up through the outer one's
        # body.
        spans.sort(key=lambda s: (s[1] - s[0], s[0]))

        # Width alone is not enough: an element whose endpoint column
        # sits exactly at another element's centre would send its riser
        # straight through that element's body -- the one crossing a
        # hop cannot express. Such a pair is ordered explicitly: the
        # element in the way must go above, so the riser never reaches
        # it. (Off-centre crossings land on leads and get hops.)
        above: Dict[str, set] = {}   # name -> names it must sit above
        for lo_a, hi_a, ea in spans:
            for lo_b, hi_b, eb in spans:
                if ea.name == eb.name:
                    continue
                for c in (lo_a, hi_a):
                    if lo_b < c < hi_b and 2 * c == lo_b + hi_b:
                        above.setdefault(eb.name, set()).add(ea.name)

        # Kahn's walk over those constraints, keeping the width sort as
        # the tie-break; a cycle (mutual centre hits) falls back to the
        # sorted order for whatever remains.
        ordered: List[Tuple[int, int, Element]] = []
        pending = list(spans)
        placed_names: set = set()
        while pending:
            pick = next(
                (s for s in pending
                 if above.get(s[2].name, set()) <= placed_names),
                pending[0])
            pending.remove(pick)
            placed_names.add(pick[2].name)
            ordered.append(pick)
        spans = ordered

        placed: List[Tuple[int, int, int]] = list(stubs)
        # A column that carries something down into the band below the
        # node row -- a grounded element, an op-amp's input or output
        # riser -- blocks the row above it too: an element spanning
        # straight over it on the node row would sit on the descending
        # wire's junction and read as connected to it. A zero-width
        # interval conflicts only with spans that contain the column
        # strictly, which is exactly the case to push up.
        for c in self.elem_col.values():
            placed.append((c, c, 0))
        for e in self.opamps:
            for n in (_op_up(e), e.fields[2]):
                c = self.node_col.get(n)
                if c is not None:
                    placed.append((c, c, 0))
        for lo, hi, e in spans:
            lvl = max((self.level[a] + 1 for a in above.get(e.name, ())
                       if a in self.level), default=0)
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
            a = self.node_col.get(_op_up(e))
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
    to size the rail, or the wire drawn here would dangle.

    When the *inverting* input is the grounded one (`o,1,0,o`), the
    pins swap: the non-inverting input takes the upper position and
    its node's column, and the inverting one drops to the rail."""
    n_out = e.fields[2]
    up_node = _op_up(e)                             # wired to the top row
    flip = up_node != e.fields[1]                   # n- grounded, pins swap
    dn_node = e.fields[1] if flip else e.fields[0]  # rail, or its own row
    up_sign, dn_sign = ("+", "−") if flip else ("−", "+")
    x_in = lay.px(lay.node_col[up_node]) if up_node in lay.node_col \
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
    cv.obstacle(tx, mid - h / 2, tx + w, mid + h / 2)
    cv.text(tx + 13, y_minus + 5, up_sign, "middle")
    cv.text(tx + 13, y_plus + 5, dn_sign, "middle")
    # The feedback loop drawn when the output cannot go right (below)
    # passes over the triangle's top, where the name normally sits, so
    # the name yields the spot and moves under the body instead.
    loop = x_out < tx + w + 12
    cv.text(tx + w / 2,
            mid + h / 2 + 16 if loop else mid - h / 2 - 8, e.name)

    # upper input: straight down from its node, then in
    cv.wire(x_in, lay.y_top, x_in, y_minus)
    cv.wire(x_in, y_minus, tx, y_minus)
    # When several op-amps hang off one input node they share that
    # vertical wire, so the branch to this one is a T-junction and needs
    # a dot -- but only if another op-amp continues on past it.
    if any(o.name != e.name and _op_up(o) == up_node
           and lay.op_lane.get(o.name, 0) > lane for o in lay.opamps):
        cv.dot(x_in, y_minus)
    # lower input: out to the left, then down to the rail (or up to its
    # own node row if it is not grounded)
    x_p = x_in - 30 - lane * 16
    cv.wire(tx, y_plus, x_p, y_plus)
    src = lay.op_src.get(e.name)
    if src is not None:
        # The stage's driving source, drawn in the input drop itself:
        # nothing else touches this input node, so the textbook picture
        # -- input straight down through the source to ground -- is
        # available. The node still gets its name, beside the drop.
        if _ground_node(src) == src.n1:
            _draw_element(cv, src, x_p, y_plus, x_p, lay.y_bot)
        else:
            _draw_element(cv, src, x_p, lay.y_bot, x_p, y_plus)
        cv.text(x_p + 6, y_plus - 6, dn_node, "start")
        grounded_at: Optional[float] = x_p
    elif dn_node == "0":
        cv.wire(x_p, y_plus, x_p, lay.y_bot)
        grounded_at = x_p
    else:
        grounded_at = None
        # 16px below the node row: far enough under a row-0 element's
        # body (zigzags reach 9px down) that the parallel run reads as
        # a separate wire rather than a graze.
        xp_node = lay.px(lay.node_col[dn_node])
        cv.wire(x_p, y_plus, x_p, lay.y_top + 16)
        cv.wire(x_p, lay.y_top + 16, xp_node, lay.y_top + 16)
        cv.wire(xp_node, lay.y_top + 16, xp_node, lay.y_top)
    # output: up to its node on the top row. When the output node's
    # column is not comfortably right of the triangle -- above all the
    # follower written `o1,1,2,2`, whose output *is* its inverting
    # input -- the straight run would slice back through the body, so
    # the wire loops over the top instead: out of the tip, up past the
    # inverting lead, and back to the column it belongs to.
    tip = tx + w
    if not loop:
        cv.wire(tip, mid, x_out, mid)
        cv.wire(x_out, mid, x_out, lay.y_top)
    else:
        # 12px above the triangle's top vertex -- measured from the
        # body, not the inverting lead, or the wire grazes the corner.
        xl, yl = tip + 14, mid - h / 2 - 12
        cv.wire(tip, mid, xl, mid)
        cv.wire(xl, mid, xl, yl)
        cv.wire(xl, yl, x_out, yl)
        if abs(x_out - x_in) < 0.5:
            # Joins the inverting input's own riser: a real junction.
            cv.dot(x_out, yl)
        else:
            cv.wire(x_out, yl, x_out, lay.y_top)
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
        # The ground symbol is drawn raw rather than as wires: its bars
        # are decoration, and the wire pass would otherwise mistake the
        # stem meeting the first bar for a T-junction and dot it.
        stem_and_bars = ['<path d="M{0:g} {1:g} L{0:g} {2:g}"/>'.format(
            gx0, y_bot, y_bot + 12)]
        for i, half in enumerate((11.0, 7.0, 3.0)):
            yy = y_bot + 12 + i * 4
            stem_and_bars.append('<path d="M{0:g} {1:g} L{2:g} {1:g}"/>'
                                 .format(gx0 - half, yy, gx0 + half))
        cv.raw("".join(stem_and_bars),
               (gx0 - 11, y_bot), (gx0 + 11, y_bot + 20))
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

    # 7. the caption block, below the drawing: values too long to
    #    letter at their element (the element keeps its name, see
    #    _draw_element), then the mutual inductances -- `m` couples two
    #    *elements*, not two nodes, so there is no honest place to put
    #    it on the circuit itself; a dashed tie between the two coils
    #    just reads as another wire.
    #    The coupling polarity, though, does belong on the circuit: a
    #    dot at each coupled coil's n1 terminal, which is what the
    #    solver's sign convention means in schematic notation (see
    #    `_coupling_dot`).
    for e in lay.mutuals:
        for coil in (e.n1, e.n2):
            if coil in segs:
                _coupling_dot(cv, *segs[coil])
    captions = []
    drawn = set(segs) | {src.name for src in lay.op_src.values()}
    for e in elements:
        if e.kind == "m" or e.name not in drawn:
            continue
        val = _pretty(e)
        if len(val) > CAPTION_LEN:
            captions.append("{0} = {1}".format(e.name, val))
    captions.extend("{0} = {1}  (couples {2} and {3})".format(
        e.name, _pretty(e), e.n1, e.n2) for e in lay.mutuals)
    if captions:
        cx, cy = cv.x0, cv.y1 + 26
        for i, line in enumerate(captions):
            cv.text(cx, cy + i * 17, line, "start")

    # 8. emit the collected wires -- merged, with junction dots at every
    #    T-joint and a semicircular hop wherever two wires cross without
    #    connecting.
    cv.flush()

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
# * A non-grounded op-amp `+` input is routed just under the node row;
#   where it crosses another wire the crossing is drawn as a hop, but a
#   dense multi-amp circuit can still accumulate several hops.
# * Two-port blocks (z/y/h/g/a/b) and the transformer `t` draw as a
#   labelled box, without their port parameters.
