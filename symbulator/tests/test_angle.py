"""Polar phasors written with the angle sign.

`(20<30 degrees)` is how every circuits textbook writes a phasor and how
versions 7 and 8 accept one. It becomes a rectangular *number* here, not
`20*exp(I*pi/6)`, and that choice is the whole point of the feature: SymPy
cannot reduce `exp(I*pi*130/180)` to a closed form, so an exponential
source is carried unevaluated through every mesh equation. AS7's Example
12.12 written that way was killed by the app's 25-second limit; written
in rectangular form it solves in about one.

Exactness is given up deliberately -- `100<0` is 100.0, not 100. A phasor
angle is a measurement, and the alternative is circuits that do not solve.
"""
import cmath
import math

import sympy as sp

from symbulator import ac
from symbulator.si_prefix import expand_value, safe_sympify

ANGLE = "\u2220"
DEGREE = "\u00b0"
ORDINAL = "\u00ba"          # looks identical, used 20 times in the 2023 docs


def _value(text):
    return complex(safe_sympify(expand_value(text)))


def test_a_phasor_becomes_its_rectangular_form():
    got = _value(f"20{ANGLE}30{DEGREE}")
    assert abs(got - cmath.rect(20, cmath.pi / 6)) < 1e-9


def test_a_negative_angle():
    got = _value(f"208{ANGLE}-110{DEGREE}")
    assert abs(got - cmath.rect(208, math.radians(-110))) < 1e-9


def test_both_degree_characters_are_accepted():
    assert (_value(f"440{ANGLE}120{DEGREE}")
            == _value(f"440{ANGLE}120{ORDINAL}"))


def test_an_en_dash_reads_as_a_minus():
    # The 2023 documentation writes negative angles with an en dash.
    assert (_value(f"100{ANGLE}\u2013120{DEGREE}")
            == _value(f"100{ANGLE}-120{DEGREE}"))


def test_the_right_angles_are_clean():
    """cos(90 degrees) is 6.1e-17 in floating point, and a source value
    carrying 1e-17 puts dust in every answer after it."""
    assert _value(f"100{ANGLE}90{DEGREE}") == 100j
    assert _value(f"100{ANGLE}0{DEGREE}") == 100 + 0j


def test_the_parenthesised_form_from_the_documentation():
    assert abs(_value(f"(20{ANGLE}30{DEGREE})")
               - cmath.rect(20, cmath.pi / 6)) < 1e-9


def test_a_circuit_of_polar_sources_solves_and_solves_quickly():
    """AS7's Example 12.12, the circuit that started this.

    Its answers are in print in the version 7 documentation: the line
    current 9.106 at 168.48 degrees and the phase current 5.500 at 172.47.
    """
    res = ac(f"e0a,0,ag,(208{ANGLE}130{DEGREE}):"
             f"eb0,bg,0,(208{ANGLE}-110{DEGREE}):"
             "rla,ag,ad,2+5j:rlb,bg,bd,2+5j:rlc,0,cd,2+5j:"
             "rab,ad,bd,50:rbc,bd,cd,30j:rca,cd,ad,-40j", omega=1)
    for key, mag, ang in (("i_rlb", 9.106, 168.48), ("i_rbc", 5.500, 172.47)):
        z = complex(sp.N(res.values[key]))
        assert abs(abs(z) - mag) < 0.01
        assert abs(math.degrees(cmath.phase(z)) - ang) < 0.01
