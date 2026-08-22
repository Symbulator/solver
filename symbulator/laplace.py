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


def t2s(expr_t, t: sp.Symbol = T, s: sp.Symbol = S) -> sp.Expr:
    """Laplace transform of a time-domain expression -- ports `t2s()`.
    Use this to prepare a source value for `fd()`/`tr()`, e.g.
    `t2s("5")` for a 5 V step, or hand-write it directly ("5/s")."""
    expr = sp.sympify(expr_t)
    result = sp.laplace_transform(expr, t, s, noconds=True)
    return sp.simplify(result)


def s2t(expr_s, s: sp.Symbol = S, t: sp.Symbol = T) -> sp.Expr:
    """Inverse Laplace transform of an s-domain expression -- ports
    `s2t()`."""
    expr = sp.sympify(expr_s)
    return sp.simplify(sp.inverse_laplace_transform(expr, s, t))


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
    s_domain = fd(desc, params=params, equations=equations,
                  unknowns=unknowns, conditions=conditions, suffix=suffix)
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
