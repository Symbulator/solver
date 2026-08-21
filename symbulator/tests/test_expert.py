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


# -- equations written on derived quantities -------------------------------
# The quantities in analysis._derived (branch voltage v_<element>, power
# p_<element>, and the r_/z_ a source sees) are computed after the system is
# solved, so the solver knows nothing about them. Before these, an equation
# naming one introduced a free variable of the same name that satisfied
# itself, leaving the circuit one equation short -- the answer came back
# correct but parametrized, with nothing to say the constraint had been
# ignored. solve_circuit now stamps the defining equation instead.

def test_equation_on_r_of_a_source_constrains_the_circuit():
    # From the documentation's own expert-mode example: the source sees
    # 12k and R3 carries 6 mA, which pins e = 72 V and rx = 2 k.
    res = ex("e,1,0,e:r1,1,2,rx:r2,2,3,4'k:r3,3,0,6'k", "dc",
             equations=["r_e = 12000", "i_r3 = 0.006"],
             unknowns=["e", "rx"])
    assert sp.simplify(res.values["e"] - 72) == 0
    assert sp.simplify(res.values["rx"] - 2000) == 0


def test_derived_definition_agrees_with_what_derived_computes():
    # The definitions in engine._derived_definition duplicate the formulas
    # in analysis._derived; this is the guard against the two drifting.
    # Ask for r_e as a constraint, then check the value _derived reports
    # afterwards is the one that was asked for.
    res = ex("e,1,0,e:r1,1,2,rx:r2,2,3,4'k:r3,3,0,6'k", "dc",
             equations=["r_e = 12000", "i_r3 = 0.006"],
             unknowns=["e", "rx"])
    assert sp.simplify(res.values["r_e"] - 12000) == 0


def test_equation_on_branch_voltage():
    # v_r2 names the drop across r2, not a node -- half of 12 V puts the
    # unknown leg at 4k, matching the fixed one.
    res = dc("e1,1,0,12:r1,1,2,4'k:r2,2,0,rb",
             equations=["v_r2 = 6"], unknowns=["rb"])
    assert sp.simplify(res.values["rb"] - 4000) == 0


def test_equation_on_dc_power():
    # 8 mW in the lower leg of a 12 V divider with 4k on top: rb = 2k
    # (8k is the other root; solve() returns one of the two).
    res = dc("e1,1,0,12:r1,1,2,4'k:r2,2,0,rb",
             equations=["p_r2 = 0.008"], unknowns=["rb"])
    assert sp.simplify(res.values["rb"] - 2000) == 0


def test_equation_on_impedance_seen_in_ac():
    res = ac("e1,1,0,10:r1,1,2,100:l1,2,0,lx", omega=1000,
             equations=["z_e1 = 100 + 100*I"], unknowns=["lx"])
    assert sp.simplify(res.values["lx"] - sp.Rational(1, 10)) == 0


def test_equation_on_op_amp_power():
    res = dc("e1,1,0,1:r1,1,2,1'k:r2,2,3,rf:o1,0,2,3",
             equations=["p_o1 = -0.002"], unknowns=["rf"])
    assert sp.simplify(res.values["rf"] - 2000) == 0


def test_ac_power_equation_is_refused_not_silently_ignored():
    # s_/p_/ap_ in AC are defined through conjugation and cannot go into
    # the system. Refusing beats the silent phantom this all guards against.
    for bad in ("s_e1 = 5", "ap_e1 = 5", "p_e1 = 5"):
        with pytest.raises(CircuitError):
            ac("e1,1,0,10:r1,1,2,100:l1,2,0,lx", omega=1000, equations=[bad])


def test_explicit_unknowns_still_win_over_the_inference():
    # r_b here is a component value, not "the r_ of an element named b" --
    # there is no element b, and it is listed under unknowns either way.
    res = dc("e1,1,0,12:r1,1,2,4'k:r2,2,0,r_b",
             equations=["v_2 = 6"], unknowns=["r_b"])
    assert sp.simplify(res.values["r_b"] - 4000) == 0


# -- equations on quantities recorded in `known` ---------------------------

def test_equation_on_a_known_source_current():
    # A j source's current is stamped into `known`, not solved for, so it
    # was phantomed the same way. Substituting the stamped value makes the
    # equation constrain the source's own symbolic value.
    res = dc("j1,0,1,jx:r1,1,0,1'k", equations=["i_j1 = 0.005"], unknowns=["jx"])
    assert sp.simplify(res.values["jx"] - sp.Rational(5, 1000)) == 0
    assert sp.simplify(res.v("1") - 5) == 0


def test_redundant_equation_on_a_known_current_is_harmless():
    res = dc("j1,0,1,5:r1,1,0,1'k", equations=["i_j1 = 5"])
    assert sp.simplify(res.v("1") - 5000) == 0


def test_contradictory_equation_on_a_known_current_is_reported():
    with pytest.raises(CircuitError):
        dc("j1,0,1,5:r1,1,0,1'k", equations=["i_j1 = 7"])
