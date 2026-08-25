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

import symbulator as sb

from symbulator import fd, tr


def test_expert_unknown_survives_the_inverse_transform():
    """AS2's step-source problem: find the amplitude given v_c(t).

    The circuit is a 2 ohm resistor and a 1 F capacitor fed by a step of
    unknown height. Told that v_c = 1 - exp(-t/2), the height is 1 V.
    """
    res = tr("e1,1,0,a*u(t):r,1,2,2:c,2,0,1,0",
             equations=["1/s-2/(2*s+1) = v_c"], unknowns=["a"])
    assert res.values["a"] == 1
    t = sb.t
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
    t = sb.t
    assert sp.simplify(res.values["i_c1"] - sp.exp(-t)) == 0


def test_fd_and_tr_agree_on_the_scalar():
    """fd solved it correctly all along; tr must report the same."""
    desc = "e1,1,0,a*u(t):r,1,2,2:c,2,0,1,0"
    eqs, unks = ["1/s-2/(2*s+1) = v_c"], ["a"]
    from symbulator.laplace import _sources_to_s
    assert fd(_sources_to_s(desc), equations=eqs, unknowns=unks).values["a"] \
        == tr(desc, equations=eqs, unknowns=unks).values["a"]


def test_tr_reads_an_added_equation_in_the_time_domain():
    """The equation is written the way the answers are shown.

    Roberto's rule, 26 Aug 2026: everything typed into expert mode in TR
    is in the time domain. The calculator sidestepped the question by
    removing TR from expert mode altogether -- its prompt offers
    "1:DC 2:AC 3:FD" -- so there is no precedent to match, only a choice
    to make.

    AS2's step-source problem, with the known voltage written plainly in
    t rather than converted with t2s first.
    """
    res = tr("e1,1,0,a*u(t):r,1,2,2:c,2,0,1,0",
             equations=["1-e^(-t/2) = v_c"], unknowns=["a"])
    assert res.values["a"] == 1


def test_a_steady_level_in_an_added_equation_is_a_step():
    """`i_r1 = 5` means five amps from t = 0, not an impulse of five.

    In the s-domain that is 5/s, and the conversion supplies the /s so
    the reader does not have to.
    """
    res = tr("e1,1,0,a:r1,1,0,1", equations=["i_r1 = 5"], unknowns=["a"])
    assert res.values["a"] == 5


def test_an_equation_already_in_s_is_left_alone():
    """A reader who converted it themselves is not converted twice."""
    res = tr("e1,1,0,a*u(t):r,1,2,2:c,2,0,1,0",
             equations=["1/s-2/(2*s+1) = v_c"], unknowns=["a"])
    assert res.values["a"] == 1


def test_a_condition_on_a_parameter_is_not_a_waveform():
    """`x = 3` fixes a symbol in the circuit; it is not a signal.

    Dividing it by s -- the treatment a steady level gets -- would make
    the source 3/s**2, a ramp. The rule looks for an answer name on one
    side before treating a relation as being about a waveform.
    """
    res = tr("e1,1,0,x*u(t):r,1,2,2:c,2,0,1,0", conditions=["x = 3"])
    t = sb.t
    assert sp.simplify(res.values["v_2"] - (3 - 3 * sp.exp(-t / 2))) == 0


def test_the_transforms_read_strings_the_way_everything_else_does():
    """t2s("5*u(t)") has to work -- the docstring advertises strings.

    Both functions used bare sp.sympify, which knows none of Symbulator's
    notation. "5*u(t)" made an undefined function of u, "2'k" would not
    parse, and "1-e^(-t/2)" read the caret as XOR and e as a symbol,
    yielding 1 - 1/e**(t/2). Those failures were silent before the domain
    checks: they came back as unevaluated LaplaceTransforms rather than
    as errors.
    """
    from symbulator import t2s, s2t

    assert t2s("5") == 5 / sb.s
    assert t2s("5*u(t)") == 5 / sb.s
    assert t2s("2'k") == 2000 / sb.s
    assert t2s("delta(t)") == 1
    assert sp.simplify(t2s("1-e^(-t/2)") - 1 / (sb.s * (2 * sb.s + 1))) == 0
    assert sp.simplify(s2t("1/(s+1)") - sp.exp(-sb.t)) == 0


def test_a_transform_in_the_wrong_direction_is_refused():
    """Both ends are checked, and the message says which end failed."""
    from symbulator import t2s, s2t
    from symbulator.elements import CircuitError

    # already in the target domain -- nothing to transform
    for call, arg in ((t2s, "1/s"), (s2t, "exp(-t)")):
        try:
            call(arg)
        except CircuitError as exc:
            assert "already in" in str(exc), str(exc)
        else:
            raise AssertionError(f"{call.__name__}({arg}) should be refused")

    # no closed form -- SymPy hands back an unevaluated transform
    try:
        t2s("1/t")
    except CircuitError as exc:
        assert "does not evaluate" in str(exc), str(exc)
    else:
        raise AssertionError("t2s(1/t) should be refused")
