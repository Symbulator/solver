"""
Tests for t2s()/s2t()/tr(): a known Laplace transform pair (step
function), that s2t(t2s(x)) round-trips, and tr() against two classic
transient responses with known closed-form solutions -- an RC charging
from a step input, and an RL circuit's natural response from a nonzero
initial inductor current -- plus that a 0 F capacitor stays open in fd()
too (not just dc/ac), matching engine.py's design note."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import sympy as sp

from symbulator import fd, tr, t2s, s2t
from symbulator.laplace import S as s, T as t


def approx_eq(a, b, tol=1e-6):
    diff = sp.simplify(sp.N(a) - sp.N(b))
    return abs(complex(diff)) < tol


def test_t2s_step():
    assert sp.simplify(t2s("5") - 5 / s) == 0


def test_s2t_roundtrip_step():
    assert sp.simplify(s2t("5/s") - 5) == 0


def test_rc_charging_step_response():
    R, C = 1000, 1e-6
    res = fd(f"e1,1,0,5/s:r1,1,2,{R}:c1,2,0,{C}")
    tau = R * C
    expected_vc = 5 * (1 - sp.exp(-t / tau))
    time_res = tr(f"e1,1,0,5/s:r1,1,2,{R}:c1,2,0,{C}", variables=["v_2"])
    got = time_res["v_2"]
    for tv in (0.0005, 0.001, 0.005):
        got_num = complex(got.subs(t, tv))
        exp_num = complex(expected_vc.subs(t, tv))
        assert abs(got_num - exp_num) < 1e-4


def test_tr_reads_a_bare_constant_source_as_a_step():
    """`e1,1,0,5` in TR is a 5 V step, not 5.delta(t).

    Issue #77: tr() moves each source into the s-domain itself, so a
    constant becomes value/s. Writing `5/s` by hand must give the same
    answer, since a value already in s is left alone -- which is what
    makes the two spellings interchangeable in TR and why the UI stopped
    warning about the first one.
    """
    R, C = 1000, 1e-6
    bare = tr(f"e1,1,0,5:r1,1,2,{R}:c1,2,0,{C}", variables=["v_2"])["v_2"]
    explicit = tr(f"e1,1,0,5/s:r1,1,2,{R}:c1,2,0,{C}",
                  variables=["v_2"])["v_2"]
    expected = 5 * (1 - sp.exp(-t / (R * C)))
    for tv in (0.0005, 0.001, 0.005):
        got = complex(bare.subs(t, tv))
        assert abs(got - complex(explicit.subs(t, tv))) < 1e-9
        assert abs(got - complex(expected.subs(t, tv))) < 1e-4
    # The distinguishing property: an impulse response decays to zero,
    # a step response settles at the source value.
    assert abs(complex(bare.subs(t, 1.0)) - 5) < 1e-6


def test_rl_natural_response_initial_condition():
    # Series R-L discharge loop: l1 (0 -> node2) with initial current I0,
    # r1 (node2 -> 0). Classic result: i_l1(t) = I0 * exp(-R t / L).
    L, R, I0 = 0.2, 100, 3
    res = fd(f"l1,0,2,{L},{I0}:r1,2,0,{R}")
    expected_s = I0 / (s + R / L)
    assert approx_eq(res.i("l1"), expected_s)

    time_res = tr(f"l1,0,2,{L},{I0}:r1,2,0,{R}", variables=["i_l1"])
    expected_t = I0 * sp.exp(-R * t / L)
    for tv in (0.0, 0.001, 0.005):
        got_num = complex(time_res["i_l1"].subs(t, tv))
        exp_num = complex(expected_t.subs(t, tv))
        assert abs(got_num - exp_num) < 1e-6


def test_fd_zero_valued_capacitor_still_open():
    # Regression: the dc/ac capacitor-open fix should carry over to fd.
    res = fd("e1,1,0,9/s:r1,1,2,1000:c1,2,0,0")
    assert sp.simplify(res.i("c1")) == 0


def test_time_symbol_is_exported_and_result_at_substitutes_by_name():
    # tr() answers use Symbol("t", positive=True); a bare Symbol("t") is a
    # different symbol, so subs() on it silently did nothing. Now the
    # solver's own symbol is exported, and Result.at() matches by name.
    import sympy as sp
    import symbulator as sb
    res = sb.tr("e1,1,0,5/s:r1,1,2,1000:c1,2,0,1e-6", variables=["v_2"])
    want = 5 * (1 - sp.exp(-1))
    assert abs(res["v_2"].subs(sb.t, 0.001) - want) < 1e-9
    assert abs(res.at("v_2", t=0.001) - want) < 1e-9
    assert abs(res.at(t=0.001)["v_2"] - want) < 1e-9
    # Non-negative rather than strictly positive: DiracDelta of a
    # strictly positive argument evaluates to 0, which erased every
    # impulse. t >= 0 is also what the one-sided transform is
    # defined on.
    assert sb.t.is_nonnegative and not sb.t.is_positive
    assert sb.s == sp.Symbol("s")
    # The trap itself is unchanged (SymPy semantics), documented, not
    # hidden: a hand-built t is a different symbol whatever its
    # assumptions, and subs() on it does nothing at all.
    assert res["v_2"].subs(sp.Symbol("t"), 0.001) == res["v_2"]
