"""Dependent sources that reference a quantity the solver never solves for.

An element's current is usually an unknown, so `2*i_r1` on a source just
works. Two quantities are not unknowns:

  * a capacitor's current, which is stamped straight into `known` as an
    expression in the node voltages, and
  * any element's *voltage*, which is derived as v(n1) - v(n2) only when
    the answers are reported.

Referencing either from a source value used to leave a free symbol that no
equation constrained. sympy then answered every quantity in terms of it --
`i_cx = i_cx*(0.9655 + 0.4138j) + 2.897 + 1.241j` -- which reads as a
solved circuit rather than a failed one, and is why it went unnoticed. The
answers below are AS7's, computed by hand.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import sympy as sp

from symbulator import ac


def polar(z):
    """`z` as (magnitude, degrees), the way `aa` reports it.

    Deliberately unrounded: rounding here once turned a 3.26 mA answer
    into 3.3 mA and failed a test that was actually correct."""
    z = complex(sp.N(z))
    return abs(z), float(sp.deg(sp.atan2(z.imag, z.real)).evalf())


def test_current_controlled_source_reads_a_capacitor_current():
    """AS7's Example 10.1: i_x = 7.59 angle 108.4 deg.

    The controlled source names `i_cx`, and cx is a capacitor -- so the
    current it names is a `known` expression, not an unknown.
    """
    res = ac("e1,1,0,20:r1,1,2,10:cx,2,0,.1:l1,2,3,1:j1,0,3,2*i_cx:l2,3,0,.5", 4)
    mag, ang = polar(res.i("cx"))
    assert abs(mag - 7.59) < 0.01
    assert abs(ang - 108.4) < 0.05
    # The whole point: nothing symbolic survives.
    assert not sp.sympify(res.i("cx")).free_symbols


def test_voltage_controlled_source_reads_an_element_voltage():
    """AS7's Practice Problem 10.1: v1 = 11.33 angle 60.02 deg,
    v2 = 33.02 angle 57.13 deg. The source names `v_rx`, which is a
    derived quantity rather than an unknown."""
    res = ac("j1,0,1,10:rx,1,0,2:c1,1,2,.2:l1,2,0,2:r1,2,3,4:e1,3,0,3*v_rx", 2)
    m1, a1 = polar(res.v("1"))
    m2, a2 = polar(res.v("2"))
    assert abs(m1 - 11.33) < 0.01 and abs(a1 - 60.02) < 0.05
    assert abs(m2 - 33.02) < 0.01 and abs(a2 - 57.13) < 0.05
    assert not sp.sympify(res.v("1")).free_symbols


def test_controlled_source_chain_resolves():
    """AS7's Example 10.13, where the controlled source reads the current
    of a capacitor that is itself between two other elements: v_ro is
    1.55 angle -95.18 deg and i_co is 3.26 angle -3.74 deg mA."""
    res = ac("e1,1,0,(8∠-40°):r1,1,2,4'k:co,2,0,2'µ:"
             "l1,2,3,50'm:j1,0,3,.5*i_co:ro,3,0,2'k", 1000)
    mv, av = polar(res.v("ro"))
    mi, ai = polar(res.i("co"))
    assert abs(mv - 1.55) < 0.01 and abs(av + 95.18) < 0.05
    assert abs(mi - 3.26e-3) < 1e-5 and abs(ai + 3.74) < 0.05
