"""Mutual inductance between impedances given in jOhms.

A textbook writes a coupled pair one of two ways: two inductors in
henries, or two impedances already in jOhms. The second is described here
as `r` elements with imaginary values, coupled by an `m` whose value is
imaginary too -- and the port only ever stamped the first kind, so the
second was accepted, solved, and silently answered with no current at all
in the secondary.

`symbv8s8` couples `r` elements when the tool is ac, adding the mutual
term without a jw factor because a value in jOhms is already an
impedance:

    v(n1) - v(n2) = Z*i_self + sum(M * i_other)

The expected values below are the ones printed in the Symbulator 7 and 8
documentation, which Roberto derived by hand.
"""
import sympy as sp

from symbulator import ac


def _polar(z, digits=4):
    """Magnitude and angle in degrees, as the `aa` tool reports them."""
    z = sp.N(sp.sympify(z))
    return float(sp.Abs(z)), float(sp.deg(sp.arg(z)))


def test_as7_example_13_1_coupled_impedances():
    res = ac("e1,1,0,12:r1,1,2,-4j:r2,2,0,5j:m,r2,r3,3j:r3,3,0,6j:r4,3,0,12",
             omega=1)
    mag, ang = _polar(res.values["i_r2"])
    assert abs(mag - 13.02) < 0.01 and abs(ang - (-49.4)) < 0.01
    mag, ang = _polar(res.values["i_r4"])
    assert abs(mag - 2.910) < 0.01 and abs(ang - 14.04) < 0.01


def test_as7_practice_problem_13_1_coupled_impedances():
    res = ac("e1,1,0,200*exp(j*pi/4):r1,1,2,4:r2,2,0,8j:"
             "m,r2,r3,1j:r3,0,o,5j:r4,o,0,10", omega=1)
    mag, ang = _polar(res.values["v_o"])
    assert abs(mag - 20.00) < 0.01 and abs(ang - (-134.43)) < 0.01


def test_the_secondary_actually_carries_current():
    """The shape of the bug, pinned directly: without the coupling the
    secondary is isolated and its current solves to exactly zero."""
    res = ac("e1,1,0,12:r1,1,2,-4j:r2,2,0,5j:m,r2,r3,3j:r3,3,0,6j:r4,3,0,12",
             omega=1)
    assert res.values["i_r3"] != 0


def test_coupled_inductors_in_henries_still_work():
    """The kind that was already ported, so the change cannot have moved it."""
    res = ac("e1,1,0,12:la,1,0,2:m,la,lb,1:lb,3,0,2:r3,3,0,10", omega=1)
    assert res.values["i_r3"] != 0
