"""
Tests for ex(), the "expert mode" dispatcher: that it routes to the
matching dc()/ac()/fd() analysis and produces identical answers, accepts
the calculator's own 1/2/3 domain shorthand, and rejects both an unknown
domain and the "tr" domain it deliberately doesn't support (see
dispatch.py's module docstring for why transient is excluded)."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import sympy as sp
import pytest

from symbulator import ex, dc, ac, fd
from symbulator.elements import CircuitError


def approx_eq(a, b, tol=1e-9):
    diff = sp.simplify(sp.N(a) - sp.N(b))
    return abs(complex(diff)) < tol


def test_ex_dc_matches_dc():
    a = ex("e1,1,0,5:r1,1,2,1'k:r2,2,0,1'k", "dc")
    b = dc("e1,1,0,5:r1,1,2,1'k:r2,2,0,1'k")
    assert approx_eq(a.v("2"), b.v("2"))


def test_ex_numeric_shorthand():
    a = ex("e1,1,0,5:r1,1,2,1'k:r2,2,0,1'k", "1")
    assert approx_eq(a.v("2"), 2.5)


def test_ex_ac_requires_omega():
    with pytest.raises(ValueError):
        ex("e1,1,0,5:r1,1,0,100", "ac")


def test_ex_ac_matches_ac():
    a = ex("e1,1,0,10:r1,1,2,100:l1,2,0,0.1", "ac", omega=1000)
    b = ac("e1,1,0,10:r1,1,2,100:l1,2,0,0.1", omega=1000)
    assert approx_eq(a.v("2"), b.v("2"))


def test_ex_unknown_domain_raises():
    with pytest.raises(ValueError):
        ex("r1,1,0,1'k", "bogus")


def test_ex_has_no_transient_mode():
    # The calculator's ex() prompt is "Analysis? 1:DC 2:AC 3:FD" -- there
    # is no transient option, and this port matches it. Use tr() directly.
    with pytest.raises(ValueError):
        ex("l1,0,2,0.2,3:r1,2,0,100", "tr", variables=["i_l1"])
    with pytest.raises(ValueError):
        ex("l1,0,2,0.2,3:r1,2,0,100", "4")


def test_ex_fd_dispatch():
    res = ex("e1,1,0,5/s:r1,1,2,1000:c1,2,0,1e-6", "3")
    assert "v_2" in res.values
