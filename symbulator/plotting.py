"""
Numeric sampling for the two plotting tools (time-domain and Bode).

This module deliberately stops at plain numbers: it runs `tr()`/`fd()`,
lambdifies the result against NumPy, and returns lists of floats. It
does not import matplotlib or draw anything -- the package's job ends
at the math, the same boundary `dc()`/`ac()`/`fd()`/`tr()` already
draw. The web and local front ends turn these numbers into an actual
picture (see symbulator_ui.py's plot_time_ui / bode_ui).

NumPy is imported lazily, inside each function, rather than at module
level -- the same reasoning as `si_prefix._allowed_namespace`'s local
`import sympy`: `import symbulator` must not require NumPy just because
this module exists, since dc()/ac()/tr() and everything else never
touch it. That matters most for the Pyodide/offline build, where every
extra package is a separate download the user has to fetch before the
page can even boot.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

import sympy as sp

from .analysis import fd
from .laplace import S, T, tr


class PlotError(ValueError):
    """Raised when a solved expression can't be turned into a numeric
    plot -- either the requested variable doesn't exist, or it still
    depends on a symbol other than t/s (a component value or expert-mode
    unknown that was never pinned to a number)."""


def _require_numeric(expr: sp.Expr, key: str, free_of: sp.Symbol) -> None:
    free = expr.free_symbols - {free_of}
    if free:
        names = ", ".join(sorted(str(s) for s in free))
        raise PlotError(
            f"'{key}' still depends on {names}, which has no numeric value -- "
            f"pin it with a condition (e.g. \"{sorted(free, key=str)[0]} = 1'k\") "
            f"before plotting."
        )


def time_samples(
    desc: str, key: str, t_max: float, t_min: float = 0.0, n: int = 400,
    params: Optional[dict] = None, equations=None, unknowns=None,
    conditions=None, suffix: str = "ask",
) -> Tuple[List[float], List[float]]:
    """Sample a `tr()` result numerically over `[t_min, t_max]`. `key` is
    a solved variable name like "v_2" or "i_r1" (see `tr()`'s
    docstring). Returns `(t_values, y_values)` as plain float lists,
    ready to hand to any plotting library."""
    import numpy as np

    if t_max <= t_min:
        raise PlotError("The time range's end must be after its start.")
    result = tr(desc, params=params, variables=[key], equations=equations,
                unknowns=unknowns, conditions=conditions, suffix=suffix)
    if key not in result.values:
        raise PlotError(
            f"'{key}' could not be transformed to the time domain -- it may "
            f"not exist, or its inverse Laplace transform has no closed form."
        )
    expr = result.values[key]
    _require_numeric(expr, key, T)

    f = sp.lambdify(T, expr, modules=["numpy"])
    t_values = np.linspace(t_min, t_max, n)
    y_raw = f(t_values)
    # A t-independent result (e.g. a plain constant) lambdifies to a bare
    # scalar rather than an array; broadcast it so the caller always gets
    # one y per t.
    y_values = np.real(np.broadcast_to(np.asarray(y_raw, dtype=complex), t_values.shape))
    return t_values.tolist(), y_values.tolist()


def bode_samples(
    desc: str, key: str, f_min: float, f_max: float, n: int = 200,
    params: Optional[dict] = None, equations=None, unknowns=None,
    conditions=None, suffix: str = "ask",
) -> Tuple[List[float], List[float], List[float]]:
    """Sample a `fd()` result's magnitude (dB) and phase (degrees) across
    a logarithmic sweep from `f_min` to `f_max` Hz (s = j*2*pi*f). `key`
    is a solved variable name like "v_2" or "z_e1". Returns
    `(freq_values, mag_db, phase_deg)` as plain float lists."""
    import numpy as np

    if f_min <= 0 or f_max <= 0:
        raise PlotError("Bode frequencies must be positive (Hz).")
    if f_max < f_min:
        raise PlotError("The frequency range's end must not be before its start.")
    result = fd(desc, params=params, equations=equations, unknowns=unknowns,
                conditions=conditions, suffix=suffix)
    if key not in result.values:
        raise PlotError(f"'{key}' was not found in the s-domain solution.")
    expr = result.values[key]
    _require_numeric(expr, key, S)

    f = sp.lambdify(S, expr, modules=["numpy"])
    freq_values = np.logspace(np.log10(f_min), np.log10(f_max), n)
    s_values = 1j * 2 * np.pi * freq_values
    h_raw = f(s_values)
    h_values = np.broadcast_to(np.asarray(h_raw, dtype=complex), s_values.shape)
    with np.errstate(divide="ignore"):
        mag_db = 20 * np.log10(np.abs(h_values))
    phase_deg = np.angle(h_values, deg=True)
    return freq_values.tolist(), mag_db.tolist(), phase_deg.tolist()
