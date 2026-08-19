"""
Tests for expert-mode extras (`equations`/`unknowns`/`conditions`,
solve_circuit's port of the calculator's "Add equations / Add unknowns /
Add conditions" prompts): solving for a symbolic component value, that a
new symbol in an extra equation is auto-detected as an unknown, that
extra equations accept the calculator's unit shorthand, that conditions
substitute at solve time, that the same extras work through ex(), and
that a malformed condition raises."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import sympy as sp
import pytest

from symbulator import dc, ac, ex
from symbulator.elements import CircuitError


def test_extra_equation_solves_for_symbolic_component():
    # 12V source, 4k on top, unknown r_b on the bottom; forcing v_2 = 6
    # (half the supply) must find r_b = 4k. The component symbol has to
    # be listed as an unknown, same as the TI's "Add unknowns" prompt.
    res = dc("e1,1,0,12:r1,1,2,4'k:r2,2,0,r_b",
             equations=["v_2 = 6"], unknowns=["r_b"])
    assert sp.simplify(res.values["r_b"] - 4000) == 0


def test_new_symbol_in_extra_equation_is_auto_unknown():
    # A brand-new symbol in the equation itself (a derived quantity)
    # becomes an unknown automatically -- no unknowns list needed.
    res = dc("e1,1,0,12:r1,1,2,4'k:r2,2,0,2'k", equations=["pout = v_2*i_r2"])
    # v_2 = 4, i_r2 = 2mA -> pout = 8 mW
    assert sp.simplify(res.values["pout"] - sp.Rational(1, 125)) == 0


def test_extra_equation_accepts_unit_shorthand():
    # The original ran its SI-prefix expander over added equations too.
    res = dc("e1,1,0,12:r1,1,2,4'k:r2,2,0,r_b",
             equations=["r_b = 4'k"], unknowns=["r_b"])
    assert sp.simplify(res.v("2") - 6) == 0


def test_conditions_substitute_at_solve_time():
    # Symbolic divider pinned down by conditions (the TI's | operator).
    res = dc("e1,1,0,vin:r1,1,2,r_a:r2,2,0,r_b",
             conditions=["vin = 12", "r_a = 4'k", "r_b = 2'k"])
    assert sp.simplify(res.v("2") - 4) == 0


def test_expert_mode_via_ex_dispatcher():
    res = ex("e1,1,0,12:r1,1,2,4'k:r2,2,0,r_b", "dc",
             equations=["v_2 = 6"], unknowns=["r_b"])
    assert sp.simplify(res.values["r_b"] - 4000) == 0


def test_extra_equation_in_ac():
    # Symbolic inductance chosen so the current magnitude has a known
    # value: |i| = 10/sqrt(100^2 + (w L)^2); force wL = 100 via equation.
    res = ac("e1,1,0,10:r1,1,2,100:l1,2,0,lx", omega=1000,
             equations=["1000*lx = 100"])
    assert sp.simplify(res.values["lx"] - sp.Rational(1, 10)) == 0


def test_bad_condition_raises():
    with pytest.raises(CircuitError):
        dc("e1,1,0,12:r1,1,0,1'k", conditions=["r_a"])
