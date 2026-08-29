"""
SPICE netlist translation, both directions (#160).

`to_spice(desc)` turns a Symbulator circuit description into a generic
ngspice-compatible netlist; `from_spice(text)` reads the linear subset of
a SPICE netlist back into Symbulator notation. Both return
`(text, warnings)`: the translation never fails on an untranslatable
element -- it leaves it out (as a `*` comment on export, dropped on
import) and says so in the warnings, so the reader always gets the part
that does translate.

The single most dangerous difference between the notations is the mega/
milli trap: Symbulator's `1'M` is mega, but in SPICE `1M` (any case) is
*milli* and mega is `1MEG`. Both directions here spell it out explicitly.

What translates:

    Symbulator -> SPICE          SPICE -> Symbulator
    r/l/c  -> R/L/C (+IC=)       R/L/C (+IC=) -> r/l/c
    e      -> V                  V (bare or DC value) -> e
    j      -> I                  I (bare or DC value) -> j
    s      -> V...0 (0V source)  E/G (VCVS/VCCS) -> e/j with v_* value
    m      -> K (numeric L only) F/H (CCCS/CCVS) -> j/e with i_* value
                                 K -> m (numeric L only)

Everything else -- the ideal op-amp `o`, the ideal transformer `t`, the
two-port blocks `z/y/h/g/a/b`, SPICE's diodes/transistors/subcircuits,
waveform sources (SIN/PULSE/PWL/...), and symbolic values on export --
is reported in the warnings instead of being mistranslated.

Node names pass through unchanged apart from case folding; ground is `0`
on both sides.
"""
from __future__ import annotations

import math
import re
from typing import List, Optional, Tuple

from .elements import parse_circuit, CircuitError
from .si_prefix import safe_sympify

# ---------------------------------------------------------------------------
# Shared: number formatting and suffix tables
# ---------------------------------------------------------------------------

# Symbulator prefix -> SPICE suffix. Note mega: 'M -> MEG, never M.
# Peta and atto have no SPICE suffix and fall back to e-notation.
_SPICE_SUFFIX = {
    12: "T", 9: "G", 6: "MEG", 3: "K",
    -3: "M", -6: "U", -9: "N", -12: "P", -15: "F",
}

# SPICE suffix -> power of ten. SPICE is case-insensitive: M and m are
# both milli; mega must be spelled MEG. MIL is 25.4e-6 (a thousandth of
# an inch) and converts to a plain number.
_SPICE_SUFFIX_IN = {
    "t": 12, "g": 9, "meg": 6, "k": 3,
    "m": -3, "u": -6, "µ": -6, "n": -9, "p": -12, "f": -15,
}

# Symbulator's own suffix letters for from-SPICE output (exponent -> 'x).
_SYMB_PREFIX = {
    12: "T", 9: "G", 6: "M", 3: "k",
    -3: "m", -6: "u", -9: "n", -12: "p", -15: "f",
}

_NUM_RE = re.compile(
    r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)(meg|mil|[tgkmunpfµ])?"
    r"[a-zµ]*$",
    re.IGNORECASE,
)


def _spice_number(value: float) -> str:
    """Format a float the way a SPICE reader expects: a suffix when one
    fits cleanly, plain decimal for near-unit values, e-notation
    otherwise. Milli is always written as a plain decimal -- this
    module never emits `M`, so its output cannot feed the mega/milli
    confusion."""
    if value == 0:
        return "0"
    if 0.001 <= abs(value) < 1000:
        return f"{value:.6g}"
    exp = math.floor(math.log10(abs(value)) / 3) * 3
    if exp in _SPICE_SUFFIX and exp != -3:
        mant = value / 10 ** exp
        text = f"{mant:.6g}"
        if "e" not in text and "E" not in text:
            return f"{text}{_SPICE_SUFFIX[exp]}"
    return f"{value:.6g}"


def _parse_spice_number(token: str) -> Optional[float]:
    """Read a SPICE value token -- number, optional suffix, optional
    trailing unit letters (`10kOhm`). None if it isn't one."""
    m = _NUM_RE.match(token.strip())
    if not m:
        return None
    number, suffix = m.group(1), (m.group(2) or "").lower()
    value = float(number)
    if suffix == "mil":
        return value * 25.4e-6
    if suffix:
        value *= 10 ** _SPICE_SUFFIX_IN[suffix]
    return value


def _symb_number(value: float) -> str:
    """Format a float in Symbulator notation: `12'm`-style when a prefix
    fits cleanly, plain decimal for near-unit values."""
    if value == 0:
        return "0"
    if 0.01 <= abs(value) < 1000:
        return f"{value:.6g}"
    exp = math.floor(math.log10(abs(value)) / 3) * 3
    if exp in _SYMB_PREFIX:
        mant = value / 10 ** exp
        text = f"{mant:.6g}"
        if "e" not in text and "E" not in text:
            return f"{text}'{_SYMB_PREFIX[exp]}"
    return f"{value:.6g}"


def _numeric(expr_text: str) -> Optional[float]:
    """The value as a float if it is a plain number (no free symbols),
    else None. Runs through the solver's own guarded sympify, so the
    same expressions the solver accepts are accepted here."""
    try:
        expr = safe_sympify(expr_text, reserve_imaginary=False)
    except Exception:
        return None
    if expr.free_symbols:
        return None
    try:
        return float(expr)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Symbulator -> SPICE
# ---------------------------------------------------------------------------

# Symbulator kind letter -> SPICE element letter, for renaming. `e1`
# becomes `V1`: the kind letter is replaced, the rest of the name rides
# along. Kinds absent here have no SPICE counterpart.
_KIND_TO_SPICE = {"r": "R", "l": "L", "c": "C", "e": "V", "j": "I"}


def to_spice(desc: str) -> Tuple[str, List[str]]:
    """Translate a Symbulator circuit description to a SPICE netlist.

    Returns `(netlist, warnings)`. Untranslatable elements are emitted
    as `*` comment lines and reported; the netlist always carries a
    title line and `.end`, so what does translate is ready to paste
    into ngspice or LTspice."""
    elements = parse_circuit(desc)  # raises CircuitError on bad input
    lines: List[str] = ["* Translated from Symbulator notation"]
    warnings: List[str] = []
    used_names = set()

    # Inductor values, for the mutual-inductance coupling factor.
    l_values = {el.name: _numeric(el.value) for el in elements
                if el.kind == "l"}

    def unique(name: str) -> str:
        base = name
        n = 2
        while name.lower() in used_names:
            name = f"{base}{n}"
            n += 1
        used_names.add(name.lower())
        return name

    def skip(el, why: str) -> None:
        lines.append(f"* {el.name},{','.join(el.fields)}  <- {why}")
        warnings.append(f"{el.name}: {why}")

    for el in elements:
        if el.kind in _KIND_TO_SPICE:
            value = el.value
            num = _numeric(value)
            if num is None:
                skip(el, "value '%s' is not a plain number; SPICE needs "
                         "numeric values (dependent sources and symbolic "
                         "values are not translated yet)" % value)
                continue
            name = unique(_KIND_TO_SPICE[el.kind] + el.name[1:])
            line = f"{name} {el.n1} {el.n2} {_spice_number(num)}"
            if el.kind in ("l", "c"):
                ic = _numeric(el.ic)
                if ic:
                    line += f" IC={_spice_number(ic)}"
            lines.append(line)
        elif el.kind == "s":
            # A 0 V source is SPICE's own idiom for a short (and its
            # ammeter). The name keeps the `s`: `s1` -> `Vs1`.
            name = unique("V" + el.name)
            lines.append(f"{name} {el.n1} {el.n2} 0")
        elif el.kind == "m":
            l1, l2 = el.fields[0], el.fields[1]
            v1, v2 = l_values.get(l1), l_values.get(l2)
            mval = _numeric(el.fields[2])
            if v1 and v2 and mval is not None:
                k = mval / math.sqrt(v1 * v2)
                name = unique("K" + el.name[1:])
                lines.append(f"{name} L{l1[1:]} L{l2[1:]} {k:.6g}")
                if k > 1:
                    warnings.append(
                        f"{el.name}: coupling factor came out {k:.4g} > 1 "
                        f"(M larger than sqrt(L1*L2)); SPICE will reject it")
            else:
                skip(el, "mutual inductance needs numeric values for M "
                         "and both inductors to compute SPICE's coupling "
                         "factor k")
        elif el.kind == "o":
            skip(el, "ideal op-amp has no SPICE primitive")
        elif el.kind == "t":
            skip(el, "ideal transformer has no SPICE primitive")
        else:  # two-port blocks z/y/h/g/a/b
            skip(el, "two-port block has no SPICE equivalent")

    lines.append(".end")
    return "\n".join(lines), warnings


# ---------------------------------------------------------------------------
# SPICE -> Symbulator
# ---------------------------------------------------------------------------

_NAME_OK = re.compile(r"[^a-z0-9_]")


def _symb_name(spice_name: str, kind: str) -> str:
    """Map a SPICE element name to a Symbulator one of the given kind:
    replace the type letter, keep the rest, fold case, and replace any
    character the parser would refuse (#159)."""
    rest = _NAME_OK.sub("_", spice_name[1:].lower())
    return kind + rest


def _v_of(node: str) -> str:
    """The node-voltage term for a controlling node; ground contributes
    nothing."""
    return "0" if node == "0" else f"v_{node}"


def _diff(np: str, nn: str) -> str:
    """`(v_a - v_b)` with ground folded away."""
    a, b = _v_of(np), _v_of(nn)
    if b == "0":
        return a
    if a == "0":
        return f"(-{b})"
    return f"({a} - {b})"


def from_spice(text: str) -> Tuple[str, List[str]]:
    """Translate the linear subset of a SPICE netlist into Symbulator
    notation, one element per line.

    Returns `(description, warnings)`. Elements and directives outside
    the subset are dropped and reported, never silently mistranslated."""
    warnings: List[str] = []
    out: List[str] = []

    # Join continuation lines, strip comments, keep order.
    raw_lines: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            continue
        if stripped.startswith("+") and raw_lines:
            raw_lines[-1] += " " + stripped[1:].strip()
        else:
            raw_lines.append(stripped)

    if not raw_lines:
        raise CircuitError("The SPICE netlist is empty.")

    # Two passes: inductor values first, so a K line can be resolved no
    # matter where it appears.
    l_values = {}
    for line in raw_lines:
        parts = line.split()
        if parts and parts[0][0] in "lL" and len(parts) >= 4:
            val = _parse_spice_number(parts[3])
            if val is not None:
                l_values[parts[0].lower()] = val

    in_subckt = False
    first_line = True
    for line in raw_lines:
        tokens = line.split()
        head = tokens[0]
        kind = head[0].lower()

        # Directives.
        if head.startswith("."):
            word = head.lower()
            if word == ".subckt":
                in_subckt = True
                warnings.append(f"'{line}': subcircuits are not translated; "
                                f"its contents were skipped")
            elif word == ".ends":
                in_subckt = False
            elif word not in (".end",):
                warnings.append(f"'{line}': directive ignored (Symbulator "
                                f"picks the analysis in the app instead)")
            first_line = False
            continue
        if in_subckt:
            continue

        if first_line:
            # Classic netlists open with a free-text title line. Try the
            # first line as an element quietly; if it isn't one, call it
            # the title and say only that.
            trial: List[str] = []
            parsed = _element_from_spice(tokens, l_values, trial)
            if parsed is None:
                warnings.append(f"'{line}': read as the netlist's title line")
            else:
                out.append(parsed)
                warnings.extend(trial)
            first_line = False
            continue
        parsed = _element_from_spice(tokens, l_values, warnings)
        if parsed:
            out.append(parsed)

    if not out:
        raise CircuitError(
            "No translatable elements found in the SPICE netlist. "
            + (" ".join(warnings) if warnings else ""))
    return "\n".join(out), warnings


def _element_from_spice(tokens: List[str], l_values: dict,
                        warnings: List[str]) -> Optional[str]:
    """One SPICE element line -> one Symbulator element line, or None
    (with a warning appended) when it cannot be translated."""
    head = tokens[0]
    kind = head[0].lower()
    line = " ".join(tokens)

    if kind in ("r", "l", "c") and len(tokens) >= 4:
        n1, n2 = tokens[1].lower(), tokens[2].lower()
        val = _parse_spice_number(tokens[3])
        if val is None:
            warnings.append(f"'{line}': value '{tokens[3]}' not understood; "
                            f"element dropped")
            return None
        name = _symb_name(head, kind)
        fields = [name, n1, n2, _symb_number(val)]
        for tok in tokens[4:]:
            if tok.upper().startswith("IC="):
                ic = _parse_spice_number(tok[3:])
                if ic is not None:
                    fields.append(_symb_number(ic))
        return ",".join(fields)

    if kind in ("v", "i") and len(tokens) >= 3:
        n1, n2 = tokens[1].lower(), tokens[2].lower()
        rest = tokens[3:]
        upper = [t.upper() for t in rest]
        value = None
        if rest and _parse_spice_number(rest[0]) is not None:
            value = _parse_spice_number(rest[0])
        elif "DC" in upper and upper.index("DC") + 1 < len(rest):
            value = _parse_spice_number(rest[upper.index("DC") + 1])
        waveform = next((t.split("(")[0] for t in upper
                         if t.split("(")[0] in ("SIN", "PULSE", "PWL",
                                                "EXP", "SFFM", "AM")), None)
        if value is None:
            warnings.append(f"'{line}': no plain or DC value found"
                            + (f" (waveform sources like {waveform} are not "
                               f"translated)" if waveform else "")
                            + "; element dropped")
            return None
        if waveform:
            warnings.append(f"'{line}': only the DC value was kept; the "
                            f"{waveform} waveform was not translated")
        name = _symb_name(head, "e" if kind == "v" else "j")
        return f"{name},{n1},{n2},{_symb_number(value)}"

    if kind in ("e", "g") and len(tokens) >= 6:
        # VCVS / VCCS: name n+ n- nc+ nc- gain. The Symbulator name
        # keeps the SPICE type letter (`E1` -> `ee1`), so it can never
        # collide with an independent source (`V1` -> `e1`).
        gain = _parse_spice_number(tokens[5])
        if gain is None:
            warnings.append(f"'{line}': gain '{tokens[5]}' not understood; "
                            f"element dropped")
            return None
        name = ("e" if kind == "e" else "j") + _NAME_OK.sub("_", head.lower())
        ctrl = _diff(tokens[3].lower(), tokens[4].lower())
        return f"{name},{tokens[1].lower()},{tokens[2].lower()},{gain:.6g}*{ctrl}"

    if kind in ("f", "h") and len(tokens) >= 5:
        # CCCS / CCVS: name n+ n- Vsource gain. Same naming rule:
        # `F1` -> `jf1`, `H1` -> `eh1`.
        gain = _parse_spice_number(tokens[4])
        vname = tokens[3]
        if gain is None or vname[0].lower() != "v":
            warnings.append(f"'{line}': not in the 'name n+ n- Vsource "
                            f"gain' form; element dropped")
            return None
        name = ("j" if kind == "f" else "e") + _NAME_OK.sub("_", head.lower())
        ctrl = "i_" + _symb_name(vname, "e")
        return f"{name},{tokens[1].lower()},{tokens[2].lower()},{gain:.6g}*{ctrl}"

    if kind == "k" and len(tokens) >= 4:
        kval = _parse_spice_number(tokens[3])
        l1, l2 = tokens[1].lower(), tokens[2].lower()
        if kval is None or l1 not in l_values or l2 not in l_values:
            warnings.append(f"'{line}': coupling needs a numeric k and "
                            f"both inductors present; element dropped")
            return None
        m = kval * math.sqrt(l_values[l1] * l_values[l2])
        name = _symb_name(head, "m")
        return f"{name},{_symb_name(l1, 'l')},{_symb_name(l2, 'l')},{_symb_number(m)}"

    described = {
        "d": "diodes", "q": "bipolar transistors", "m": "MOSFETs",
        "j": "JFETs", "x": "subcircuit calls", "b": "behavioral sources",
        "t": "transmission lines", "s": "switches", "w": "switches",
        "u": "uniform RC lines", "o": "lossy lines",
    }.get(kind)
    if described:
        warnings.append(f"'{line}': {described} have no Symbulator "
                        f"equivalent; element dropped")
    else:
        warnings.append(f"'{line}': not recognised as a SPICE element; "
                        f"line dropped")
    return None
