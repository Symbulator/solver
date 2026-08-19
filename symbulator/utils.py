"""
Small standalone helpers ported from Symbulator: `pr()` (parallel
combination) and `gain()` (two-port gain figures). `pf()` (power factor)
is a simplified adaptation -- the original read implicit per-element
`v<name>`/`i<name>` calculator variables and a fixed sign convention
per element type; here it just takes an explicit voltage/current phasor
pair, which is the part of the original logic that generalizes cleanly.
"""

from __future__ import annotations

from typing import Sequence, Union

import sympy as sp


def pr(*impedances: Union[str, sp.Expr]) -> sp.Expr:
    """Parallel combination of any number of impedances (or admittances'
    reciprocals) -- ports `pr(alpha_z)`. If any argument is exactly 0,
    the combination is 0 (a short circuit dominates a parallel network),
    matching the original's explicit zero-check."""
    if len(impedances) == 1 and isinstance(impedances[0], (list, tuple)):
        impedances = tuple(impedances[0])
    values = [sp.sympify(z) for z in impedances]
    if not values:
        raise ValueError("pr() requires at least one impedance.")
    if len(values) == 1:
        return values[0]
    if any(v == 0 for v in values):
        return sp.Integer(0)
    total = sp.Integer(0)
    for v in values:
        total += 1 / v
    return sp.simplify(1 / total)


def pf(voltage: Union[str, sp.Expr], current: Union[str, sp.Expr]):
    """Power factor magnitude and leading/lagging direction for a
    voltage/current phasor pair, using the |cos(angle(V) - angle(I))|
    convention from the original `pf()`."""
    v = sp.sympify(voltage)
    i = sp.sympify(current)
    angle_diff = sp.arg(v) - sp.arg(i)
    value = sp.re(sp.cos(angle_diff))
    side = sp.sign(angle_diff)
    magnitude = round(float(sp.Abs(value)), 5)
    if side < 0:
        direction = "leading"
    elif side > 0:
        direction = "lagging"
    else:
        direction = "in phase"
    return f"pf: {magnitude} {direction}"


def gain(v1: Union[str, sp.Expr], i1: Union[str, sp.Expr],
         v2: Union[str, sp.Expr], i2: Union[str, sp.Expr]) -> dict:
    """Voltage/current/power gain and input impedance from in/out
    voltage-current pairs -- ports `gain()`."""
    v1, i1, v2, i2 = (sp.sympify(x) for x in (v1, i1, v2, i2))
    av = sp.simplify(v2 / v1)
    ai = sp.simplify(i2 / i1)
    ap = sp.simplify(sp.re(-av * sp.conjugate(ai)))
    zi = sp.simplify(v1 / i1)
    return {"Av": av, "Ai": ai, "Ap": ap, "Zi": zi}
