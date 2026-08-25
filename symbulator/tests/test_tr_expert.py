"""Expert mode in TR, and the scalar it used to swallow.

tr() inverse-Laplace-transforms what fd() solved. Every element current
and node voltage is a function of s and wants transforming; an
expert-mode unknown -- the amplitude of a source, say -- is a plain
number and does not.

Transforming it anyway is not harmless. inverse_laplace_transform(1, s, t)
is DiracDelta(t), and the time symbol here is declared positive, so
DiracDelta collapses to 0. A step amplitude the s-domain solve had
correctly found to be 1 was reported as 0, with no error: expert mode
looked as though it simply did not work in TR.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import sympy as sp

from symbulator import fd, tr


def test_expert_unknown_survives_the_inverse_transform():
    """AS2's step-source problem: find the amplitude given v_c(t).

    The circuit is a 2 ohm resistor and a 1 F capacitor fed by a step of
    unknown height. Told that v_c = 1 - exp(-t/2), the height is 1 V.
    """
    res = tr("e1,1,0,a*u(t):r,1,2,2:c,2,0,1,0",
             equations=["1/s-2/(2*s+1) = v_c"], unknowns=["a"])
    assert res.values["a"] == 1
    t = sp.Symbol("t", positive=True)
    expected = 1 - sp.exp(-t / 2)
    assert sp.simplify(res.values["v_c"] - expected) == 0


def test_a_scalar_answer_is_not_turned_into_an_impulse():
    """The narrow version: any s-independent value passes through.

    The equation is in the s-domain, as TR's always are -- so a steady
    5 A is written 5/s. The source height then solves to the scalar 5 and
    must arrive in the time domain unchanged rather than as
    5*DiracDelta(t), which under a positive t is zero.

    Written as `i_r1 = 5` it would instead be asking for an impulse of
    5, whose answer really is a = 5*s; that is a different question, not
    a bug, and it is why the documentation converts with t2s first.
    """
    res = tr("e1,1,0,a:r1,1,0,1", equations=["i_r1 = 5/s"], unknowns=["a"])
    got = res.values["a"]
    assert got == 5
    assert not got.has(sp.Symbol("s"))


def test_tr_still_transforms_the_waveforms():
    """The guard must not stop real answers being transformed."""
    res = tr("e1,1,0,1:r1,1,2,1:c1,2,0,1", variables=["i_c1"])
    t = sp.Symbol("t", positive=True)
    assert sp.simplify(res.values["i_c1"] - sp.exp(-t)) == 0


def test_fd_and_tr_agree_on_the_scalar():
    """fd solved it correctly all along; tr must report the same."""
    desc = "e1,1,0,a*u(t):r,1,2,2:c,2,0,1,0"
    eqs, unks = ["1/s-2/(2*s+1) = v_c"], ["a"]
    from symbulator.laplace import _sources_to_s
    assert fd(_sources_to_s(desc), equations=eqs, unknowns=unks).values["a"] \
        == tr(desc, equations=eqs, unknowns=unks).values["a"]
