"""
Transient (time-domain) analysis and Laplace-transform helpers: ports
`tr()`, `t2s()`, and `s2t()`.

The original called out to a separate TI-Nspire library (`lf\\ilaplace` /
`lf\\laplace`) that wasn't included in the document this was ported
from, so this port uses SymPy's own `laplace_transform` /
`inverse_laplace_transform` instead of trying to reproduce that missing
library.
"""

from __future__ import annotations

from typing import Iterable, Optional

import sympy as sp

from .analysis import Result, fd

T = sp.Symbol("t", positive=True)
S = sp.Symbol("s")
#: Public names for the same two symbols. `t` carries positive=True so
#: that inverse Laplace transforms simplify (no stray Heaviside(t)); a
#: bare sp.Symbol("t") is a *different* symbol and subs() on it silently
#: does nothing. Import these instead of re-creating them.
t = T
s = S


#: The time symbol as an expression carries it before any transform. The
#: forward transform integrates from 0 to infinity and needs no assumption
#: about t; declaring one changes what the expression *means* rather than
#: only which symbol it uses, and SymPy evaluates DiracDelta of a strictly
#: positive argument to 0 -- so an impulse source parsed against a positive
#: t is gone before the transform ever sees it.
TIME_IN = sp.Symbol("t")


def t2s(expr_t, t: sp.Symbol = None, s: sp.Symbol = S) -> sp.Expr:
    """Laplace transform of a time-domain expression -- ports `t2s()`.
    Use this to prepare a source value for `fd()`/`tr()`, e.g.
    `t2s("5")` for a 5 V step, or hand-write it directly ("5/s").

    With `t` left unset the time symbol is taken from the expression, so
    it works whichever `t` the caller's expression happens to carry. Pass
    one explicitly to override."""
    expr = sp.sympify(expr_t)
    if t is None:
        named = sorted((x for x in expr.free_symbols if x.name == "t"),
                       key=str)
        t = named[0] if named else TIME_IN
    result = sp.laplace_transform(expr, t, s, noconds=True)
    return sp.simplify(result)


def s2t(expr_s, s: sp.Symbol = S, t: sp.Symbol = T) -> sp.Expr:
    """Inverse Laplace transform of an s-domain expression -- ports
    `s2t()`."""
    expr = sp.sympify(expr_s)
    return sp.simplify(sp.inverse_laplace_transform(expr, s, t))


# --------------------------------------------------------------------------
# Time-domain source values, on the way into an s-domain solve
# --------------------------------------------------------------------------
#
# `tr()` reads its sources in the time domain; `fd()` reads them in s. That
# is the original's design, and this port lost half of it: the answers were
# transformed back but the sources were never transformed in, so every
# transient result was one integration short -- a plain `12` gave the
# impulse response where the step response was wanted.
#
# This is symbv8s5's `betatool="tr"` branch, restored. Read out of the
# version 8 document itself rather than inferred:
#
#     If betatool="tr" and inString("ej",kind) Then
#       If value <> value|t=0 Then      t2s(value)      a waveform
#       Else If type="NUM" Then         value/s         a step
#            Else if it depends on another answer:  leave it alone
#                 otherwise:                        value/s
#
# The last branch is the one worth reading twice. A controlled source's
# value is a *relation* -- `2*i_r1` says "twice whatever that current is"
# -- not a waveform, so transforming it would be meaningless. The original
# decides by substituting each node voltage and element current in turn and
# seeing whether the value changes; this does the same by looking at which
# symbols the value actually contains.

_ANSWER_PREFIXES = ("v", "i", "p", "ap", "s", "z", "r")


def _is_controlled(expr: sp.Expr, elements) -> bool:
    """Does this value refer to another element's answer?"""
    names = {str(sym) for sym in expr.free_symbols}
    if not names:
        return False
    known = set()
    for el in elements:
        for prefix in _ANSWER_PREFIXES:
            known.add(f"{prefix}_{el.name}")
            known.add(f"{prefix}{el.name}")
        for idx in (0, 1):
            if idx < len(el.fields):
                known.add(f"v_{el.fields[idx]}")
                known.add(f"v{el.fields[idx]}")
    return bool(names & known)


def _source_to_s(value: str, elements, s: sp.Symbol = S) -> str:
    """One `e`/`j` value, moved from the time domain into the s-domain."""
    from .si_prefix import expand_value, safe_sympify

    try:
        # reserve_imaginary=False: a transient circuit has no complex
        # values, so `i` in a source value is an ordinary symbol --
        # `i*delta(t)` means i amperes of impulse, not the unit. And
        # through the ordinary shorthand, or `u(t)` is still an undefined
        # function and the transform quietly declines it.
        expr = safe_sympify(expand_value(value), reserve_imaginary=False)
    except Exception:                                         # noqa: BLE001
        return value          # not an expression we can read; leave it

    time = [x for x in expr.free_symbols if x.name == "t"]

    # A waveform: anything written in terms of t. The transform picks the
    # expression's own time symbol -- forcing one it does not contain
    # makes laplace_transform treat the whole thing as a constant and
    # divide by s, which is how `t` came back as t/s instead of 1/s**2.
    if time:
        try:
            return str(t2s(expr, s=s))
        except Exception:                                     # noqa: BLE001
            return value

    # Already written in s: the reader has done the conversion, or is
    # working from an s-domain source as `fd()` would take. Leave it.
    if expr.has(s):
        return value

    if _is_controlled(expr, elements):
        return value

    # A constant, numeric or symbolic: a step of that amplitude.
    return str(expr / s)


def _sources_to_s(desc: str, s: sp.Symbol = S) -> str:
    """`desc` with every independent source value moved into the s-domain."""
    from .elements import parse_circuit

    try:
        elements = parse_circuit(desc, expand_si=False)
    except Exception:                                         # noqa: BLE001
        return desc           # let the real parse report the problem

    out, changed = [], False
    for el in elements:
        fields = list(el.fields)
        if el.kind in ("e", "j") and len(fields) >= 3:
            moved = _source_to_s(fields[2], elements, s)
            if moved != fields[2]:
                fields[2] = moved
                changed = True
        out.append(el.name + "," + ",".join(fields))
    return ":".join(out) if changed else desc


def tr(desc: str, params: Optional[dict] = None,
       variables: Optional[Iterable[str]] = None,
       t: sp.Symbol = T, equations=None, unknowns=None,
       conditions=None, suffix: str = "ask") -> Result:
    """Transient (time-domain) analysis -- ports `tr()`. Runs `fd()`
    (s-domain analysis) and then inverse-Laplace-transforms the result
    back to the time domain.

    By default every solved node voltage and element current is
    transformed; pass `variables` (an iterable of keys like "v_2" or
    "i_r1") to transform only specific ones -- useful since inverse
    Laplace transforms of complicated expressions can be slow or fail
    to find a closed form. A variable that can't be transformed is left
    out of the result rather than raising, since the rest of the
    circuit's answers are usually still valid and useful."""
    s_domain = fd(_sources_to_s(desc), params=params,
                  equations=equations, unknowns=unknowns,
                  conditions=conditions, suffix=suffix)
    keys = list(variables) if variables is not None else list(s_domain.values.keys())

    time_domain = {}
    for key in keys:
        expr = s_domain.values.get(key)
        if expr is None:
            continue
        try:
            time_domain[key] = sp.simplify(sp.inverse_laplace_transform(expr, S, t))
        except Exception:
            continue  # leave it out rather than fail the whole analysis

    return Result(domain="tr", values=time_domain)
