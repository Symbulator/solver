"""
High-level API mirroring the TI programs `dc()` and `ac()`: parse a
circuit description, solve it, and also compute the "3rd-level" derived
quantities (branch voltage, power, impedance) that Symbulator computes
after solving -- ported from the tail of `symbv8s6`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import sympy as sp

from .elements import Element, parse_circuit
from .engine import solve_circuit


@dataclass
class Result:
    """Everything `dc()`/`ac()`/`fd()`/`tr()` solved for, keyed by the same
    variable names the calculator used: `v_<node>` for a node voltage,
    `i_<name>` for an element/branch current, plus the derived `p_`/`s_`/
    `z_`/`r_` quantities computed after the solve (dc/ac only -- see
    `_derived`). `domain` records which analysis produced it ("dc", "ac",
    "fd", or "tr"), which matters because the same key means a different
    kind of number depending on domain (e.g. `v_2` is a real number in dc,
    a phasor in ac, an s-domain expression in fd, a function of t in tr)."""
    domain: str
    values: Dict[str, sp.Expr] = field(default_factory=dict)

    def __getitem__(self, key: str) -> sp.Expr:
        """result["v_2"] -- direct lookup by variable name; raises KeyError
        if that variable wasn't solved for (e.g. asking for a node that
        doesn't exist, or a `tr()` variable that couldn't be inverse-
        transformed)."""
        return self.values[key]

    def get(self, key: str, default=None):
        """Same as __getitem__ but returns `default` instead of raising
        when the key is missing."""
        return self.values.get(key, default)

    def v(self, node) -> sp.Expr:
        """Voltage at `node` (shorthand for result[f"v_{node}"])."""
        return self.values[f"v_{node}"]

    def i(self, name) -> sp.Expr:
        """Current through the element/branch called `name` (shorthand
        for result[f"i_{name}"])."""
        return self.values[f"i_{name}"]

    def __repr__(self) -> str:
        """One line per solved variable, sorted by name, so a Result
        prints legibly at the REPL or in a notebook instead of dumping an
        unordered dict."""
        lines = [f"Result(domain={self.domain!r})"]
        for k in sorted(self.values):
            lines.append(f"  {k} = {self.values[k]}")
        return "\n".join(lines)


def _node_v(solution: Dict[str, sp.Expr], node: str) -> sp.Expr:
    """Look up a node's voltage in a raw solve() dict, treating node "0"
    (ground) as the literal constant 0 even though the solver never
    creates a v_0 symbol for it. Falls back to a bare symbol (rather than
    raising) if the node was never stamped into the system -- this keeps
    `_derived` from blowing up on a malformed circuit; the missing-node
    error itself is already raised earlier, during parsing."""
    if node == "0":
        return sp.Integer(0)
    return solution.get(f"v_{node}", sp.Symbol(f"v_{node}"))


def _seen_impedance(vdiff: sp.Expr, i: sp.Expr):
    """v / (-i) for the impedance/resistance a source sees, tolerating a
    zero current. A source pushing no current is looking into an open
    circuit, so the honest answer is infinite -- but a plain division
    would either produce SymPy's `zoo` (for exact zeros) or raise
    ZeroDivisionError outright (for float zeros, since mpmath refuses).
    Returns None for the genuinely undefined 0/0 case so the caller can
    omit the quantity instead of reporting nonsense."""
    denom = sp.simplify(-i)
    if denom.is_zero:
        num = sp.simplify(vdiff)
        if num.is_zero:
            return None          # 0 V across 0 A: undefined, not infinite
        return sp.oo
    return sp.simplify(vdiff / denom)


def _derived(elements, domain: str, solution: Dict[str, sp.Expr],
             use_rms: bool = False) -> Dict[str, sp.Expr]:
    """Compute the "3rd-level" quantities the calculator derived *after*
    solving the KCL system: branch voltage (v_<name>), power (p_<name> in
    dc, or apparent/complex power s_<name> plus real average power in ac),
    and -- for sources only -- the impedance/resistance the source sees
    looking into the rest of the circuit (z_<name> / r_<name>). These are
    plain algebra on the already-solved node voltages and branch currents,
    not part of the KCL system itself, so they're computed in one pass
    here rather than inside the solver in engine.py."""
    out: Dict[str, sp.Expr] = {}
    for e in elements:
        if e.kind in "ejrcl":
            i_key = f"i_{e.name}"
            if i_key not in solution:
                continue
            i = solution[i_key]
            vdiff = sp.simplify(_node_v(solution, e.n1) - _node_v(solution, e.n2))
            # Branch voltage (voltage drop across the element) -- the
            # original stored these as v<name> on the calculator.
            out[f"v_{e.name}"] = vdiff
            if domain == "ac":
                s = vdiff * sp.conjugate(i)
                if not use_rms:
                    s = s / 2
                s = sp.simplify(s)
                out[f"s_{e.name}"] = s
                if e.kind in "ejr":
                    p = sp.simplify(sp.re(s))
                    out[f"p_{e.name}" if use_rms else f"ap_{e.name}"] = p
                    if e.kind in "ej":
                        z = _seen_impedance(vdiff, i)
                        if z is not None:
                            out[f"z_{e.name}"] = z
            else:  # dc
                out[f"p_{e.name}"] = sp.simplify(vdiff * i)
                if e.kind in "ej":
                    r = _seen_impedance(vdiff, i)
                    if r is not None:
                        out[f"r_{e.name}"] = r
        elif e.kind == "o":
            i_key = f"i_{e.name}"
            if i_key not in solution:
                continue
            i = solution[i_key]
            n_out = e.fields[2]
            vout = _node_v(solution, n_out)
            if domain == "ac":
                s = vout * sp.conjugate(-i)
                if not use_rms:
                    s = s / 2
                s = sp.simplify(s)
                out[f"s_{e.name}"] = s
                out[f"p_{e.name}" if use_rms else f"ap_{e.name}"] = sp.simplify(sp.re(s))
            else:
                out[f"p_{e.name}"] = sp.simplify(vout * (-i))
    return out


def _run(desc: str, domain: str, omega=None, params=None, use_rms: bool = False,
         equations=None, unknowns=None, conditions=None,
         suffix: str = "ask") -> Result:
    """Shared body of `dc()`/`ac()`/`fd()`: parse the circuit, solve it,
    add the derived quantities where they apply, and wrap the result.
    Kept as one function so the three public entry points stay tiny and
    can't drift out of sync with each other."""
    elements = parse_circuit(desc)
    solution = solve_circuit(elements, domain=domain, omega=omega, params=params,
                             equations=equations, unknowns=unknowns,
                             conditions=conditions, suffix=suffix)
    if domain in ("dc", "ac"):
        # Matches the original: the power/impedance "3rd-level" derived
        # quantities are only computed for dc/ac, not for fd (s-domain).
        solution.update(_derived(elements, domain, solution, use_rms=use_rms))
    return Result(domain=domain, values=solution)


def dc(desc: str, params: Optional[dict] = None, equations=None,
       unknowns=None, conditions=None, suffix: str = "ask") -> Result:
    """DC steady-state analysis. `desc` is a Symbulator-style circuit
    description string, e.g. "e1,1,0,5:r1,1,2,1k:r2,2,0,1k".
    `equations`/`unknowns`/`conditions` add expert-mode extras to the
    system before solving (see `solve_circuit`)."""
    return _run(desc, "dc", params=params, equations=equations,
                unknowns=unknowns, conditions=conditions, suffix=suffix)


def ac(desc: str, omega, params: Optional[dict] = None, use_rms: bool = False,
       equations=None, unknowns=None, conditions=None,
       suffix: str = "ask") -> Result:
    """AC steady-state (phasor) analysis at angular frequency `omega`
    (a number or a SymPy expression/symbol for a symbolic frequency)."""
    return _run(desc, "ac", omega=sp.sympify(omega), params=params,
                use_rms=use_rms, equations=equations, unknowns=unknowns,
                conditions=conditions, suffix=suffix)


def fd(desc: str, params: Optional[dict] = None, equations=None,
       unknowns=None, conditions=None, suffix: str = "ask") -> Result:
    """s-domain (Laplace) analysis -- ports `fd()`. Source values may be
    any SymPy-parseable expression in `s` (e.g. "5/s" for a DC step,
    "1" for an impulse); use `utils.t2s()` to Laplace-transform a
    time-domain source expression first if needed. `l`/`c` elements may
    carry an optional 5th field for a nonzero initial condition, e.g.
    "l1,1,2,0.1,2" for a 0.1 H inductor with 2 A of initial current."""
    return _run(desc, "fd", params=params, equations=equations,
                unknowns=unknowns, conditions=conditions, suffix=suffix)
