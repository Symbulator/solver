"""The two-port parameter term (#163): z,1,2,[p11,p12,p21,p22].

The load-bearing equivalence: a parameter term must give exactly the
answers the expert-mode conditions route gives, because it IS that route
-- the values bind to the parameter variables through the same
substitution machinery (the calculator's "store the values first").
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
import sympy as sp

from symbulator import dc
from symbulator.elements import CircuitError


BARE = "e1,1,0,10:z,1,2:rl,2,0,200"
TERM = "e1,1,0,10:z,1,2,[100,10,20,50]:rl,2,0,200"
CONDS = ["z11 = 100", "z12 = 10", "z21 = 20", "z22 = 50"]


def test_case_c_equals_expert_conditions():
    a = dc(TERM)
    b = dc(BARE, conditions=CONDS)
    for key in ("v_1", "v_2", "i_rl"):
        assert sp.simplify(a[key] - b[key]) == 0


def test_case_a_stays_symbolic():
    res = dc(BARE)
    syms = {str(s) for s in res["v_2"].free_symbols}
    assert {"z11", "z12", "z21", "z22"} <= syms


def test_tacit_term_written_out_is_a_no_op():
    a = dc("e1,1,0,10:z,1,2,[z11,z12,z21,z22]:rl,2,0,200")
    b = dc(BARE)
    assert sp.simplify(a["v_2"] - b["v_2"]) == 0


def test_user_condition_overrides_the_term():
    # An explicit `|` condition wins over the description's own value,
    # matching how the TI's with-operator overrode stored variables.
    a = dc(TERM, conditions=["z21 = 40"])
    b = dc(BARE, conditions=["z11 = 100", "z12 = 10",
                             "z21 = 40", "z22 = 50"])
    assert sp.simplify(a["v_2"] - b["v_2"]) == 0


def test_si_prefixes_and_expressions_in_the_term():
    a = dc("e1,1,0,10:z,1,2,[0.1'k,10,20,[100,100]]:rl,2,0,200")
    b = dc(BARE, conditions=["z11 = 100", "z12 = 10",
                             "z21 = 20", "z22 = 50"])
    assert sp.simplify(a["v_2"] - b["v_2"]) == 0


def test_symbolic_entries_stay_symbolic():
    # Keep the coupling terms nonzero, or v_2 is identically 0 and
    # carries no symbols at all.
    res = dc("e1,1,0,10:z,1,2,[za,10,20,zb]:rl,2,0,200")
    syms = {str(s) for s in res["v_2"].free_symbols}
    assert "za" in syms and "zb" in syms and "z11" not in syms


def test_wrong_entry_count_rejected():
    with pytest.raises(CircuitError, match="Exactly four"):
        dc("e1,1,0,10:z,1,2,[100,10,20]:rl,2,0,200")


def test_non_list_fourth_term_rejected():
    with pytest.raises(CircuitError, match="four-entry list"):
        dc("e1,1,0,10:z,1,2,100:rl,2,0,200")


def test_all_six_kinds_accept_the_term():
    # Same physical block expressed per kind is overkill here; this just
    # asserts the notation parses and solves numerically for each kind.
    per_kind = {
        "z": "[100,10,20,50]",
        "y": "[0.02,-0.01,-0.01,0.02]",
        "h": "[100,0.1,-2,0.01]",
        "g": "[0.01,0.1,2,50]",
        "a": "[2,100,0.01,1.5]",
        "b": "[2,100,0.01,1.5]",
    }
    for kind, term in per_kind.items():
        res = dc(f"e1,1,0,10:{kind},1,2,{term}:rl,2,0,200")
        assert not res["v_2"].free_symbols, (kind, res["v_2"])
