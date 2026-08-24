"""The calculator's spellings for the step and the impulse.

Versions 7 and 8 write a step as `u(t)` and an impulse with a Greek delta.
Version 9 parses through SymPy, which knows neither, so a description
copied from the older documentation failed with "'Symbol' object is not
callable". These accept both spellings unchanged.

`u` is also the micro prefix, and the rule that separates them is whether
a `(` follows: `7u` is micro, `7u(t)` is the function. That means a bare
`u` is left alone entirely, so it still works as an ordinary variable --
unlike the names in `_allowed_namespace`, which are taken from everyone.
"""
import sympy as sp

from symbulator import tr
from symbulator.elements import parse_circuit
from symbulator.si_prefix import (expand_shorthand, expand_value,
                                  safe_sympify)

DELTA = "δ"


# --------------------------------------------------------------- the rule ---

def test_u_before_a_bracket_is_the_step():
    assert expand_shorthand("V*u(t)", si=True) == "V*Heaviside(t)"


def test_u_without_a_bracket_is_left_for_the_micro_suffix():
    # Neither of these is a function call, so expand_shorthand must not
    # touch them -- `7u` is 7 micro-somethings, handled further down.
    assert expand_shorthand("7u", si=False) == "7u"
    # And through the real entry point it becomes micro, not a function.
    assert expand_value("7u") == "(7)*10**-6"
    assert expand_value("4.7u") == "(4.7)*10**-6"


def test_quoted_micro_prefix_is_untouched():
    assert expand_shorthand("7'u", si=False) == "7'u"


def test_a_leading_number_gets_its_implied_multiplication():
    # `7u(t)` is a product on the calculator. Nothing later in the chain
    # infers one, and `7Heaviside(t)` is a syntax error rather than a
    # product, so the `*` has to be put in here.
    assert expand_shorthand("7u(t)", si=True) == "7*Heaviside(t)"
    assert expand_shorthand("7*u(t)", si=True) == "7*Heaviside(t)"


def test_greek_delta_is_the_impulse():
    assert expand_shorthand(f"i*{DELTA}(t)", si=True) == "i*DiracDelta(t)"


def test_ascii_delta_works_for_keyboards_without_the_character():
    assert expand_shorthand("i*delta(t)", si=True) == "i*DiracDelta(t)"


def test_a_name_ending_in_u_is_not_a_step():
    # `vu(t)` is not the step function; only a `u` that starts a name is.
    assert expand_shorthand("vu(t)", si=True) == "vu(t)"


# ------------------------------------------------------- reaching sympify ---

def test_step_reaches_sympy_as_heaviside():
    # expand_value is the real entry point: it tries the bare suffix first
    # (so `7u` stays micro) and falls through to expand_shorthand.
    # `t` parses as a neutral symbol on purpose -- see
    # test_a_positive_t_would_erase_the_impulse below.
    assert safe_sympify(expand_value("V*u(t)")) == (
        sp.Symbol("V") * sp.Heaviside(sp.Symbol("t")))


def test_impulse_reaches_sympy_as_diracdelta():
    got = safe_sympify(expand_value(f"i*{DELTA}(t)"),
                       reserve_imaginary=False)
    assert got == sp.Symbol("i") * sp.DiracDelta(sp.Symbol("t"))


def test_u_is_still_an_ordinary_variable():
    # The regression the first attempt at this introduced: putting `u` in
    # the namespace made every `u` a function, so a source valued `u`
    # stopped parsing.
    assert safe_sympify("u") == sp.Symbol("u")
    assert parse_circuit("e1,1,0,u")[0].value == "u"


# ------------------------------------------------------------ end to end ----

def test_a_calculator_step_circuit_solves():
    both = [tr(f"e1,1,0,V*{spelling}:r,1,2,r:c,2,0,c,0").v(2)
            for spelling in ("u(t)", "Heaviside(t)")]
    assert sp.simplify(both[0] - both[1]) == 0


def test_a_calculator_impulse_circuit_solves():
    both = [tr(f"j,0,1,i*{spelling}:c,1,0,c,0:r,1,0,r").v(1)
            for spelling in (f"{DELTA}(t)", "DiracDelta(t)")]
    assert sp.simplify(both[0] - both[1]) == 0


def test_micro_suffix_still_solves_beside_a_step():
    # Both meanings of `u` in one description, which is the whole point of
    # the rule: a micro capacitor driven by a step source.
    res = tr("e1,1,0,12*u(t):r,1,2,2:c,2,0,1'u,0")
    assert res.v(2) != 0


# ------------------------------------------- kept, not replaced -------------

def test_the_typed_notation_survives_being_echoed_back():
    """Parsed but kept, like `'k` -- not replaced, like `J` in AC.

    The web app puts the echoed circuit straight back into the Circuit
    Description box. Rewriting `u(t)` to `Heaviside(t)` there would take
    the calculator's notation away from someone who deliberately typed it,
    silently, on their first Run.
    """
    for typed in ("V*u(t)", f"i*{DELTA}(t)", "2ir3", "2e^(-4t)"):
        assert expand_shorthand(typed, si=False) == typed


def test_but_it_is_expanded_on_the_way_to_being_solved():
    assert expand_shorthand("V*u(t)", si=True) == "V*Heaviside(t)"
    assert expand_shorthand("2ir3", si=True) == "2*ir3"


def test_the_bracket_shortcut_is_still_expanded_either_way():
    # Unlike the rest, `[...]` has to go unconditionally: _split_fields
    # cannot tell the shortcut's inner commas from an element's own.
    assert expand_shorthand("[1,2]", si=False) == "pr(1,2)"


# ------------------------------------------- names with digits inside -------

def test_a_digit_inside_a_name_is_not_a_multiplication():
    """`t2s(t)` must not become `t2*s(t)`.

    The implicit-multiplication rule shipped in 0.5.1 looked only at the
    character before the letter, so it split every name with a digit in the
    middle -- including t2s and s2t themselves, the two functions most
    likely to be typed into a transient source.
    """
    for name in ("t2s(t)", "s2t(1/s)", "i2r", "v2", "r2d(x)"):
        assert expand_value(name) == name


def test_the_multiplication_is_still_inserted_where_it_belongs():
    assert expand_value("2ir3") == "2*ir3"
    assert expand_value(".2v1") == ".2*v1"
    assert expand_value("2t") == "2*t"


def test_t2s_reaches_the_solver_through_a_circuit_value():
    # The whole point of putting t2s in the namespace: a transient source
    # written in the time domain, converted where it is typed.
    from symbulator import tr
    ramp = tr("j,0,1,t2s(t):c,1,0,2,0").values["v_1"]
    assert sp.simplify(ramp - sp.Symbol("t", positive=True) ** 2 / 4) == 0


def test_a_positive_t_would_erase_the_impulse():
    """Why the parsing namespace binds a neutral `t`.

    0.5.3 bound it to the solver's Symbol("t", positive=True) so that a
    hand-written `t` matched the answers. That changes what an expression
    *means*: SymPy evaluates DiracDelta of a strictly positive argument to
    zero, so an impulse source vanished before the transform ever saw it.
    """
    assert sp.DiracDelta(sp.Symbol("t", positive=True)) == 0
    assert sp.DiracDelta(sp.Symbol("t")) != 0
    # And the parsed form is the one that survives.
    assert safe_sympify(expand_value("delta(t)")) != 0


# ---------------------------------------- TR reads its sources in time ------

def _in_time(expr):
    """Answers come back in Symbol("t", positive=True); expectations here
    are written with a neutral t. Same symbol name, different assumptions,
    and subtracting them does not cancel -- so line them up first."""
    e = sp.sympify(expr)
    T = sp.Symbol("t", positive=True)
    return e.subs({x: T for x in e.free_symbols if x.name == "t"})


def _tr_gives(desc, key, expected):
    from symbulator import tr
    got = _in_time(tr(desc).values[key])
    assert sp.simplify(sp.expand(got - _in_time(expected))) == 0


def test_a_constant_source_is_a_step():
    # symbv8s5: a NUM value becomes value/s.
    _tr_gives("j,0,1,1:c,1,0,2,0", "v_1", sp.Symbol("t") / 2)


def test_a_waveform_source_is_transformed():
    # symbv8s5: a value that changes with t becomes t2s(value).
    _tr_gives("j,0,1,t:c,1,0,2,0", "v_1", sp.Symbol("t") ** 2 / 4)


def test_the_rc_step_response_is_the_step_response():
    t = sp.Symbol("t")
    _tr_gives("e1,1,0,12:r,1,2,2:c,2,0,1,0", "v_2", 12 - 12 * sp.exp(-t / 2))


def test_the_calculators_spelling_gives_the_calculators_answer():
    # AS7's Example 16.1, whose answer is in print in both the version 7
    # and version 8 documentation.
    t = sp.Symbol("t")
    _tr_gives("e1,1,0,u(t):r1,1,2,1:r2,2,o,5:c,2,0,1/3,0:l,o,0,1,0", "v_o",
              3 * sp.sqrt(2) * sp.exp(-4 * t) * sp.sin(sp.sqrt(2) * t) / 2)


def test_an_s_domain_source_is_left_alone():
    # Anything already written in s is the caller having done the
    # conversion; transforming it again would be wrong. This is also what
    # keeps every existing version 9 description working.
    t = sp.Symbol("t")
    _tr_gives("e1,1,0,5/s:r1,1,2,1000:c1,2,0,1e-6", "v_2",
              5 - 5 * sp.exp(-1000 * t))


def test_a_controlled_source_is_left_alone():
    """A controlled source's value is a relation, not a waveform.

    symbv8s5 decides this by substituting each node voltage and element
    current in turn and seeing whether the value changes; this port looks
    at which symbols the value contains. Either way `2*i_r3` must not be
    divided by s.
    """
    from symbulator.laplace import _sources_to_s
    desc = "e1,1,0,2:r3,1,2,3:r5,2,3,5:c,3,0,1:j,0,2,2*i_r3"
    assert "2*i_r3" in _sources_to_s(desc)
    assert "e1,1,0,2/s" in _sources_to_s(desc)
