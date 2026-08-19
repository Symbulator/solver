"""Reserved symbols, case folding and the SI-prefix set."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import sympy as sp
import pytest

from symbulator import dc, ac
from symbulator.elements import CircuitError, parse_circuit
from symbulator.si_prefix import safe_sympify, hijacked_names, bare_suffix_match

MICRO = "µ"   # MICRO SIGN
GREEK_MU = "μ"  # GREEK SMALL LETTER MU


# --- the imaginary unit -------------------------------------------------

@pytest.mark.parametrize("form", ["3j", "3*j", "3*i", "3*I", "3*J", "j*3"])
def test_all_imaginary_spellings_agree(form):
    assert safe_sympify(form) == 3 * sp.I


def test_bare_j_is_the_imaginary_unit():
    assert safe_sympify("j") == sp.I


def test_imaginary_works_as_an_ac_source_value():
    # A purely imaginary source, written the way an engineer would.
    res = ac("e1,1,0,j*10:r1,1,0,100", omega=1000)
    assert sp.simplify(res.v("1") - 10 * sp.I) == 0


# --- names SymPy would otherwise hijack ---------------------------------

@pytest.mark.parametrize("name", ["Q", "S", "N", "beta", "gamma", "E"])
def test_hijack_prone_names_become_plain_variables(name):
    expr = safe_sympify(name)
    assert expr.free_symbols == {sp.Symbol(name)}


def test_quality_factor_survives_a_solve():
    # Q is an assumptions object to bare sympify; here it must behave as
    # an ordinary symbolic resistance.
    res = dc("e1,1,0,10:r1,1,2,Q:r2,2,0,Q")
    assert sp.simplify(res.v("2") - 5) == 0


def test_hijacked_names_are_reported():
    found = hijacked_names("Q*2 + beta + r_load + pi + exp(1)")
    assert set(found) == {"Q", "beta"}
    assert "r_load" not in found and "pi" not in found


def test_intended_constants_still_work():
    assert safe_sympify("2*pi*1000") == 2000 * sp.pi
    assert safe_sympify("sqrt(2)") == sp.sqrt(2)
    assert safe_sympify("exp(1)") == sp.E          # Euler via exp(), not E


# --- case folding -------------------------------------------------------

def test_element_names_and_nodes_fold_to_lowercase():
    els = parse_circuit("E1,A,0,10:R1,A,B,100:RLoad,B,0,200")
    assert [e.name for e in els] == ["e1", "r1", "rload"]
    assert els[1].n1 == "a" and els[1].n2 == "b"


def test_same_name_in_different_case_is_a_duplicate():
    with pytest.raises(CircuitError):
        parse_circuit("e1,1,0,10:r1,1,2,100:R1,2,0,100")


def test_mutual_inductance_references_fold_too():
    els = parse_circuit(
        "e1,1,0,10:L1,1,2,0.1:L2,3,0,0.1:M1,L1,L2,0.05:r1,2,0,50:r2,3,0,50")
    m = next(e for e in els if e.kind == "m")
    assert m.fields[0] == "l1" and m.fields[1] == "l2"


def test_uppercase_circuit_solves_identically():
    a = dc("E1,1,0,10:R1,1,2,100:R2,2,0,100")
    b = dc("e1,1,0,10:r1,1,2,100:r2,2,0,100")
    assert sp.simplify(a.v("2") - b.v("2")) == 0


def test_values_keep_their_case():
    # 'M is mega and 'm is milli -- folding these would be catastrophic.
    els = parse_circuit("e1,1,0,5:r1,1,0,4.7'M:r2,1,0,4.7'm")
    assert els[1].fields[2] != els[2].fields[2]


# --- SI prefixes --------------------------------------------------------

def test_exa_is_gone_so_E_belongs_to_scientific_notation():
    assert bare_suffix_match("8E") is None
    assert bare_suffix_match("8E3") is None
    res = dc("e1,1,0,10:r1,1,0,8E3")
    assert abs(complex(res.i("r1")) - complex(10 / 8000)) < 1e-12


@pytest.mark.parametrize("mu", [MICRO, GREEK_MU])
def test_both_micro_characters_are_accepted(mu):
    assert bare_suffix_match(f"4.7{mu}") == ("4.7", mu)
    res = dc(f"e1,1,0,5:r1,1,0,4.7'{mu}")
    assert sp.simplify(res.i("r1") - 5 / sp.Rational(47, 10000000)) == 0


# --- packaging ----------------------------------------------------------

def test_version_is_exposed_and_well_formed():
    import symbulator
    import re as _re

    assert _re.fullmatch(r"\d+\.\d+\.\d+", symbulator.__version__)


def test_version_matches_the_installed_distribution_when_there_is_one():
    # pyproject reads __version__ at build time; if this package is
    # installed, the two must agree. Skipped when running from a source
    # tree with nothing installed.
    import symbulator
    from importlib.metadata import version, PackageNotFoundError

    try:
        installed = version("symbulator")
    except PackageNotFoundError:
        pytest.skip("symbulator is not installed in this environment")
    assert installed == symbulator.__version__
