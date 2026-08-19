"""
Validation suite: textbook circuits with known, independently
hand-calculated answers, checked against the symbulator port.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import sympy as sp
import pytest

from symbulator import dc, ac, pr
from symbulator.elements import CircuitError


def approx_eq(a, b, tol=1e-9):
    diff = sp.simplify(sp.N(a) - sp.N(b))
    return abs(complex(diff)) < tol


def test_voltage_divider_dc():
    res = dc("e1,1,0,5:r1,1,2,1'k:r2,2,0,1'k")
    assert approx_eq(res.v("2"), 2.5)
    assert approx_eq(res.i("r1"), 2.5e-3)
    assert approx_eq(res.i("r2"), 2.5e-3)


def test_voltage_divider_dc_unequal():
    # 10V across a 3k/1k divider -> node between them = 10 * 1k/(3k+1k) = 2.5V
    res = dc("e1,1,0,10:r1,1,2,3'k:r2,2,0,1'k")
    assert approx_eq(res.v("2"), 2.5)


def test_current_divider_dc():
    # 6A injected into a node with 1k and 3k to ground in parallel.
    res = dc("j1,0,1,6:r1,1,0,1'k:r2,1,0,3'k")
    expected_v = 6 * float(pr(1000, 3000))
    assert approx_eq(res.v("1"), expected_v)
    assert approx_eq(res.i("r1"), expected_v / 1000)
    assert approx_eq(res.i("r2"), expected_v / 3000)


def test_series_rlc_ac_impedance():
    R, L, C, w = 100, 0.1, 1e-6, 1000
    res = ac("e1,1,0,10:r1,1,2,100:l1,2,3,0.1:c1,3,0,1e-6", omega=w)
    z_expected = R + 1j * w * L + 1 / (1j * w * C)
    i_expected = 10 / z_expected
    assert approx_eq(res.i("e1"), -i_expected)  # e1 current defined n1->n2 = into source = -loop current
    # cross-check via voltage drop / current (r1 current is defined n1->n2, same as the loop current)
    z_measured = sp.N((res.v("1") - res.v("2")) / res.i("r1"))
    assert approx_eq(z_measured, R)


def test_opamp_inverting_amplifier_dc():
    # Vout = -(Rf/Rin) * Vin, ideal op-amp, non-inverting input grounded.
    res = dc("e1,1,0,2:rin,1,2,1'k:rf,2,3,4'k:o1,0,2,3")
    assert approx_eq(res.v("2"), 0)  # virtual ground
    assert approx_eq(res.v("3"), -8)


def test_opamp_noninverting_amplifier_dc():
    # Non-inverting amp: Vout = Vin * (1 + Rf/Rg), input applied to +.
    res = dc("e1,1,0,3:rg,2,0,1'k:rf,2,3,2'k:o1,1,2,3")
    assert approx_eq(res.v("2"), 3)  # virtual short to + input
    assert approx_eq(res.v("3"), 3 * (1 + 2000 / 1000))


def test_voltage_controlled_voltage_source_dc():
    # e2 = 2 * v_2, where v_2 is set to 5V by an upstream divider.
    res = dc("e1,1,0,10:r1,1,2,1'k:r2,2,0,1'k:e2,3,0,2*v_2:r3,3,0,500")
    assert approx_eq(res.v("2"), 5)
    assert approx_eq(res.v("3"), 10)
    assert approx_eq(res.i("r3"), 10 / 500)


def test_pr_parallel_helper():
    assert approx_eq(pr(1000, 1000), 500)
    assert approx_eq(pr(1000, 3000), 750)
    assert pr(1000, 0) == 0


def test_ideal_transformer_ac():
    # Step-down 2:1 ideal transformer, driven directly on the primary.
    res = ac("e1,1,0,10:t1,1,2,2,1:rl,2,0,100", omega=1000)
    assert approx_eq(res.v("2"), 5)
    assert approx_eq(res.i("rl"), 5 / 100)


def test_mutual_inductance_zero_coupling_isolates_secondary():
    # Secondary loop (l2 + rload) is grounded on one end so its node
    # voltages are well-defined. With M=0 it has no source of its own,
    # so it should carry no current and show 0V.
    res = ac("e1,1,0,10:l1,1,0,0.05:m1,l1,l2,0:l2,0,4,0.02:rload,4,0,50",
             omega=500)
    assert approx_eq(res.v("4"), 0)
    assert approx_eq(res.i("l2"), 0)


def test_mutual_inductance_couples_secondary():
    # Same topology with nonzero M: the secondary should now carry
    # induced current, i.e. it must NOT stay at zero.
    res = ac("e1,1,0,10:l1,1,0,0.05:m1,l1,l2,0.01:l2,0,4,0.02:rload,4,0,50",
             omega=500)
    assert abs(complex(sp.N(res.i("l2")))) > 1e-6


def test_two_port_y_parameters_as_series_resistor():
    # y-parameters of an ideal 1k series resistor between two grounded
    # ports: y11=y22=1/Z, y12=y21=-1/Z. Chaining it after a 10V source
    # into a 1k load should behave exactly like a plain voltage divider.
    params = {"y1": {"11": "0.001", "12": "-0.001", "21": "-0.001", "22": "0.001"}}
    res = dc("e1,1,0,10:y1,1,2:rl,2,0,1'k", params=params)
    assert approx_eq(res.v("2"), 5)


def test_dc_power_derived_quantity():
    res = dc("e1,1,0,5:r1,1,2,1'k:r2,2,0,1'k")
    i = float(sp.N(res.i("r1")))
    assert approx_eq(res["p_r1"], i * i * 1000)


def test_ac_complex_power_derived_quantity():
    res = ac("e1,1,0,10:r1,1,0,50", omega=1000)
    # Pure resistive load: apparent power (peak convention) = |V|^2/(2R)
    assert approx_eq(res["ap_r1"], 10**2 / (2 * 50))


def test_zero_valued_capacitor_is_open_not_short_dc():
    # Regression test for a bug found in the original TI-Basic source:
    # a 0F capacitor must behave as an open circuit, not a short.
    # e1 -- r1 -- (node2) -- c1(0F) -- gnd : node2 should float up to
    # the full source voltage (no current flows, no drop across r1).
    res = dc("e1,1,0,9:r1,1,2,1'k:c1,2,0,0")
    assert approx_eq(res.v("2"), 9)
    assert approx_eq(res.i("c1"), 0)
    assert approx_eq(res.i("r1"), 0)


def test_zero_valued_capacitor_is_open_not_short_ac():
    res = ac("e1,1,0,9:r1,1,2,1'k:c1,2,0,0", omega=1000)
    assert approx_eq(res.v("2"), 9)
    assert approx_eq(res.i("c1"), 0)


def test_nonzero_capacitor_still_open_in_dc():
    # Make sure fixing the C=0 case didn't disturb the existing
    # (already-correct) nonzero-capacitance DC behavior.
    res = dc("e1,1,0,9:r1,1,2,1'k:c1,2,0,10e-6")
    assert approx_eq(res.v("2"), 9)
    assert approx_eq(res.i("c1"), 0)


def test_parser_rejects_missing_ground():
    with pytest.raises(CircuitError):
        dc("e1,1,2,5:r1,1,2,1'k")


def test_parser_rejects_duplicate_names():
    with pytest.raises(CircuitError):
        dc("e1,1,0,5:e1,2,0,3:r1,1,2,1'k")


def test_parser_rejects_wrong_field_count():
    with pytest.raises(CircuitError):
        dc("e1,1,0,5,99:r1,1,0,1'k")


def test_thevenin_style_two_source_dc():
    # Two sources feeding a common resistor node -- solved independently
    # via superposition by hand:
    #   e1=12V through r1=2k into node A; e2=6V through r2=1k into node A;
    #   rL=3k from A to ground.
    # Node equation: (V-12)/2k + (V-6)/1k + V/3k = 0
    # Multiply by 6k: 3(V-12) + 6(V-6) + 2V = 0 -> 11V = 36+36=72 -> V=72/11
    res = dc("e1,1,0,12:r1,1,2,2'k:e2,3,0,6:r2,3,2,1'k:rl,2,0,3'k")
    assert approx_eq(res.v("2"), sp.Rational(72, 11))


def test_source_with_no_current_reports_infinite_resistance():
    # A source feeding only a capacitor pushes no DC current, so the
    # "resistance seen" is infinite. Float values used to make this
    # raise ZeroDivisionError out of mpmath instead of answering.
    res = dc("e1,1,0,5:r1,1,2,4.7'k:c1,2,0,10*u")
    assert res.i("e1").is_zero
    assert res["r_e1"] == sp.oo
    assert sp.simplify(res.v("2") - 5) == 0


def test_zero_volt_zero_current_source_omits_resistance():
    # 0 V across 0 A is undefined, not infinite -- the key is omitted
    # rather than reporting a bogus number.
    res = dc("e1,1,0,0:r1,1,2,1'k:c1,2,0,1e-6")
    assert "r_e1" not in res.values
