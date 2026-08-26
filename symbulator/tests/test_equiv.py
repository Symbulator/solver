"""
Tests for th()/er()/port(): Thevenin equivalents against a
hand-calculated voltage divider and against reconnecting the equivalent
in place of the original circuit, er() against a known series-resistance
case, and port() against known z/a-parameter values for simple networks
(including that a/z/y should all describe the same network consistently)."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import sympy as sp
import pytest

from symbulator import dc, ac, th, er, port


def approx_eq(a, b, tol=1e-9):
    diff = sp.simplify(sp.N(a) - sp.N(b))
    return abs(complex(diff)) < tol


def test_thevenin_voltage_divider_dc():
    res = th("e1,1,0,12:r1,1,2,4'k:r2,2,0,2'k", "2", "0", domain="dc")
    assert approx_eq(res.vth, 4)
    assert approx_eq(res.z, 4000 * 2000 / 6000)  # r1 || r2


def test_thevenin_matches_load_connected_dc():
    # Cross-check: connecting a known load and solving directly should
    # match the Thevenin-equivalent prediction V_load = Vth*RL/(Rth+RL).
    th_res = th("e1,1,0,12:r1,1,2,4'k:r2,2,0,2'k", "2", "0", domain="dc")
    direct = dc("e1,1,0,12:r1,1,2,4'k:r2,2,0,2'k:rl,2,0,5'k")
    predicted = th_res.vth * 5000 / (th_res.z + 5000)
    assert approx_eq(direct.v("2"), predicted)


def test_thevenin_rejects_passive_circuit():
    with pytest.raises(Exception):
        th("r1,1,0,1'k:r2,1,0,2'k", "1", "0", domain="dc")


def test_er_series_resistors():
    req = er("r1,1,2,1'k:r2,2,0,2'k", "1", "0", domain="dc")
    assert approx_eq(req, 3000)


def test_er_matches_thevenin_impedance_when_deactivated():
    # For a passive two-terminal network, er() should agree with the
    # Req you'd compute by hand for a simple series/parallel combo.
    req = er("r1,1,0,600:r2,1,0,300", "1", "0", domain="dc")  # 600 || 300 = 200
    assert approx_eq(req, 200)


def test_port_y_parameters_series_resistor():
    params = port("r1,1,2,1000", "1", "2", "y", domain="dc")
    assert approx_eq(params["11"], 0.001)
    assert approx_eq(params["12"], -0.001)
    assert approx_eq(params["21"], -0.001)
    assert approx_eq(params["22"], 0.001)


def test_port_z_parameters_t_network():
    # Classic T-network: r1 from port1 to a shared internal node, r2
    # from port2 to that same node, r3 from that node to ground.
    # Textbook result: z11=r1+r3, z22=r2+r3, z12=z21=r3.
    r1v, r2v, r3v = 100, 200, 50
    params = port(f"r1,1,3,{r1v}:r2,2,3,{r2v}:r3,3,0,{r3v}", "1", "2", "z", domain="dc")
    assert approx_eq(params["11"], r1v + r3v)
    assert approx_eq(params["22"], r2v + r3v)
    assert approx_eq(params["12"], r3v)
    assert approx_eq(params["21"], r3v)
    # z and y (of the same T-network) must be matrix inverses of each other.
    y = port(f"r1,1,3,{r1v}:r2,2,3,{r2v}:r3,3,0,{r3v}", "1", "2", "y", domain="dc")
    Y = sp.Matrix([[y["11"], y["12"]], [y["21"], y["22"]]])
    Z = sp.Matrix([[params["11"], params["12"]], [params["21"], params["22"]]])
    assert sp.simplify(Y * Z - sp.eye(2)) == sp.zeros(2, 2)


def test_port_a_parameters_round_trip():
    # Stamp an 'a' two-port element with known ABCD parameters, then
    # extract it right back out with port() on the same two nodes --
    # this checks that the element-stamping formulas (Phase 1) and the
    # extraction formulas (Phase 2) are mutually consistent.
    known = {"11": "2", "12": "50", "21": "0.01", "22": "1.5"}
    extracted = port("a1,1,2", "1", "2", "a", domain="dc", params={"a1": known})
    for key in ("11", "12", "21", "22"):
        assert approx_eq(extracted[key], sp.sympify(known[key]))


def test_port_ac_series_impedance():
    # y-parameters of a lone series R-L impedance Z = R + jwL directly
    # between the two (grounded) ports, generalizing the DC series-R
    # test above to a complex AC impedance.
    w = 500
    Z = 100 + 1j * w * 0.2
    params = port("r1,1,3,100:l1,3,2,0.2", "1", "2", "y", domain="ac", omega=w)
    assert approx_eq(params["11"], sp.simplify(1 / Z))
    assert approx_eq(params["12"], sp.simplify(-1 / Z))
    assert approx_eq(params["21"], sp.simplify(-1 / Z))
    assert approx_eq(params["22"], sp.simplify(1 / Z))


def test_th_accepts_expert_equations_and_unknowns():
    # TR5's Example 4-8 from the tutorial: the dependent source's value
    # is a derived name, vx, defined as the difference between two node
    # voltages. On the calculator that took a `Define vx=va-vb` line
    # before the th script ran; here the definition is an added equation
    # with vx as an added unknown, and it has to reach both of th()'s
    # rounds for the answers to come out in terms of vs and mu.
    mu, vs, ro = sp.symbols("mu vs ro")
    eq = th("ei,a,0,vs:ed,1,0,mu*(vx):ro,b,1,ro", "b", "0",
            equations=["vx = v_a - v_b"], unknowns=["vx"])
    assert sp.simplify(eq.vth - vs * mu / (mu + 1)) == 0
    assert sp.simplify(eq.z - ro / (mu + 1)) == 0


def test_er_accepts_an_expert_condition():
    # A condition fixes a symbol in the circuit, so the equivalent
    # resistance of two parallel resistors with a symbolic value should
    # come back as the number the condition implies.
    free = er("r1,a,0,r:r2,a,0,6", "a", "0")
    assert sp.simplify(free - sp.sympify("6*r/(r + 6)")) == 0
    fixed = er("r1,a,0,r:r2,a,0,6", "a", "0", conditions=["r = 3"])
    assert sp.simplify(fixed - sp.Rational(2)) == 0


def test_equivalents_without_expert_extras_are_unchanged():
    # The extras are optional and default to nothing, so a plain call
    # must behave exactly as it did before they existed.
    # The source value 3.3 is a float, so these answers are floats too --
    # compare the way the rest of this file does rather than exactly.
    eq = th("e,1,0,3.3:r1,1,2,66:r2,2,0,24", "2", "0")
    assert approx_eq(eq.vth, sp.Rational(33, 10) * 24 / 90)
    assert approx_eq(eq.z, sp.Rational(66 * 24, 90))
