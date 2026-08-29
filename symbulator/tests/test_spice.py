"""SPICE translation, both directions (#160).

The round-trip tests are the load-bearing ones: what to_spice writes,
from_spice must read back into a circuit the solver gives the same
answers for -- equivalence is checked by solving, not by comparing text.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
import sympy as sp

from symbulator import dc, to_spice, from_spice
from symbulator.elements import CircuitError


# --- Symbulator -> SPICE -------------------------------------------------

def test_basic_export():
    net, warns = to_spice("e1,1,0,5:r1,1,2,1'k:r2,2,0,1'k")
    lines = net.splitlines()
    assert lines[0].startswith("*")            # title line
    assert "V1 1 0 5" in lines
    assert "R1 1 2 1K" in lines
    assert "R2 2 0 1K" in lines
    assert lines[-1] == ".end"
    assert warns == []


def test_mega_is_MEG_and_milli_is_M():
    # The classic SPICE trap: 1'M (mega) must never come out as "1M",
    # which SPICE reads as one millionth of what was meant.
    net, _ = to_spice("e1,1,0,5:r1,1,0,2.2'M")
    assert "R1 1 0 2.2MEG" in net
    # And milli never comes out as "M" at all -- plain decimal instead,
    # so our output cannot feed the confusion in either direction.
    net, _ = to_spice("j1,0,1,12'm:r1,1,0,1'k")
    assert "I1 0 1 0.012" in net


def test_initial_conditions_export():
    net, _ = to_spice("e1,1,0,5:r1,1,2,1000:c1,2,0,1'u,3")
    assert "C1 2 0 1U IC=3" in net


def test_short_becomes_zero_volt_source():
    net, _ = to_spice("e1,1,0,5:r1,1,2,1'k:s1,2,3:r2,3,0,1'k")
    assert "Vs1 2 3 0" in net


def test_mutual_inductance_export():
    net, warns = to_spice(
        "e1,1,0,5:l1,1,0,0.1:l2,2,0,0.4:m1,l1,l2,0.1:r1,2,0,50")
    assert "K1 L1 L2 0.5" in net
    assert warns == []


def test_symbolic_value_warns_and_comments():
    net, warns = to_spice("e1,1,0,5:r1,1,2,1'k:r2,2,0,rb")
    assert any("rb" in w for w in warns)
    assert "* r2,2,0,rb" in net            # kept as a comment, not dropped
    assert "R2" not in net


def test_dependent_source_warns():
    net, warns = to_spice("e1,1,0,5:r1,1,2,1'k:e2,3,0,2*v_2:r3,3,0,1'k")
    assert any("e2" in w for w in warns)


def test_opamp_and_twoport_warn():
    net, warns = to_spice("e1,1,0,5:r1,1,2,1:o1,0,2,3:r2,2,3,2")
    assert any("op-amp" in w for w in warns)
    _, warns = to_spice("e1,1,0,10:y1,1,2:rl,2,0,1'k")
    assert any("two-port" in w for w in warns)


# --- SPICE -> Symbulator -------------------------------------------------

def test_basic_import():
    desc, warns = from_spice("""\
My divider
V1 1 0 5
R1 1 2 1k
R2 2 0 1k
.end
""")
    assert "read as the netlist's title line" in warns[0]
    res = dc(desc)
    assert res.v("2") == sp.Rational(5, 2)


def test_import_milli_and_meg():
    desc, _ = from_spice("V1 1 0 5\nR1 1 0 1MEG\nR2 1 0 2m\n")
    assert "r1,1,0,1'M" in desc
    assert "r2,1,0,2'm" in desc


def test_import_dc_keyword_and_waveform_warning():
    desc, warns = from_spice("V1 1 0 DC 12\nR1 1 0 1k\n")
    assert "e1,1,0,12" in desc
    desc, warns = from_spice("V1 1 0 SIN(0 1 1k)\nR1 1 0 1k\nV2 2 0 5\nR2 2 0 1k")
    assert any("SIN" in w for w in warns)
    assert "e2,2,0,5" in desc and "e1" not in desc.splitlines()[0]


def test_import_controlled_sources():
    # VCVS: E1 3 0 2 0 2.0 -> ee1 (the SPICE letter rides along, so it
    # cannot collide with V1 -> e1).
    desc, warns = from_spice(
        "V1 1 0 5\nR1 1 2 1k\nR2 2 0 1k\nE1 3 0 2 0 2\nR3 3 0 1k\n")
    assert "ee1,3,0,2*v_2" in desc
    res = dc(desc)
    assert res.v("3") == 5           # 2 * v_2 = 2 * 2.5

    # CCCS: F1 references V1's current; V1 maps to e1, so i_e1.
    desc, _ = from_spice(
        "V1 1 0 5\nR1 1 0 1k\nF1 0 2 V1 10\nR2 2 0 100\n")
    assert "jf1,0,2,10*i_e1" in desc


def test_import_coupling():
    desc, warns = from_spice(
        "V1 1 0 5\nL1 1 0 0.1\nL2 2 0 0.4\nK1 L1 L2 0.5\nR1 2 0 50\n")
    assert "m1,l1,l2,0.1" in desc
    assert warns == []


def test_import_drops_nonlinear_with_warning():
    desc, warns = from_spice(
        "V1 1 0 5\nR1 1 2 1k\nD1 2 0 mydiode\n.model mydiode D\n")
    assert any("diodes" in w for w in warns)
    assert any("directive ignored" in w for w in warns)
    assert "d1" not in desc


def test_import_subckt_skipped_whole():
    desc, warns = from_spice("""\
V1 1 0 5
R1 1 0 1k
.subckt opamp 1 2 3
R9 1 2 1k
.ends
""")
    assert "r9" not in desc
    assert any("subcircuit" in w for w in warns)


def test_import_empty_raises():
    with pytest.raises(CircuitError):
        from_spice("* nothing here\n.end\n")


# --- Round trip ----------------------------------------------------------

def test_round_trip_solves_identically():
    original = "e1,1,0,36:r1,1,2,1'k:r2,2,3,3'k:r3,3,0,2'k"
    net, warns = to_spice(original)
    assert warns == []
    back, warns2 = from_spice(net)
    assert warns2 == []
    a, b = dc(original), dc(back)
    for key in ("v_2", "v_3", "i_r1", "p_r3"):
        assert sp.simplify(a[key] - b[key]) == 0


def test_round_trip_with_ic_and_coupling():
    original = ("e1,1,0,5:r1,1,2,1000:c1,2,0,1'u,3:"
                "l1,2,0,0.1:l2,3,0,0.4:m1,l1,l2,0.1:r2,3,0,50")
    net, warns = to_spice(original)
    assert warns == []
    back, warns2 = from_spice(net)
    assert warns2 == []
    a, b = dc(original), dc(back)
    assert sp.simplify(a["v_2"] - b["v_2"]) == 0
