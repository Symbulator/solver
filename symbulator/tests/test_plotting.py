"""
Tests for the numeric sampling helpers behind the two plotting tools:
time_samples() (drives the time-domain plot) and bode_samples() (drives
the Bode plot). These check the numbers against hand-derived formulas,
not just that nothing crashes.
"""

import math
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from symbulator.plotting import time_samples, bode_samples, PlotError


def test_time_samples_rc_step_response():
    # 5V step (source given as its Laplace transform, 5/s) into a 1k/1uF
    # RC low-pass: v_2(t) = 5*(1 - exp(-t/tau)), tau = R*C = 1e-3 s.
    tau = 1000 * 1e-6
    t_max = 5 * tau
    t, y = time_samples("e1,1,0,5/s:r1,1,2,1000:c1,2,0,1e-6", "v_2",
                         t_max=t_max, n=50)
    assert len(t) == len(y) == 50
    assert t[0] == pytest.approx(0.0)
    assert t[-1] == pytest.approx(t_max)
    assert y[0] == pytest.approx(0.0, abs=1e-9)
    for ti, yi in zip(t, y):
        expected = 5 * (1 - math.exp(-ti / tau))
        assert yi == pytest.approx(expected, abs=1e-6)


def test_time_samples_rejects_bad_range():
    with pytest.raises(PlotError):
        time_samples("e1,1,0,5/s:r1,1,2,1000:c1,2,0,1e-6", "v_2",
                      t_max=0.0, t_min=0.0)


def test_time_samples_rejects_unresolved_symbol():
    # r1's value is left symbolic (no condition pins it), so v_2(t) still
    # depends on r1 and can't be sampled numerically.
    with pytest.raises(PlotError):
        time_samples("e1,1,0,5/s:r1,1,2,r1:c1,2,0,1e-6", "v_2", t_max=1e-3)


def test_bode_samples_rc_low_pass():
    # Same RC low-pass, viewed as a filter: |H(jw)| = 1/sqrt(1+(w*tau)^2).
    # At the corner frequency f_c = 1/(2*pi*tau), the magnitude is
    # -3.01 dB and the phase is -45 degrees.
    tau = 1000 * 1e-6
    f_c = 1 / (2 * math.pi * tau)
    freqs, mag_db, phase_deg = bode_samples(
        "e1,1,0,1:r1,1,2,1000:c1,2,0,1e-6", "v_2",
        f_min=f_c, f_max=f_c, n=1)
    assert mag_db[0] == pytest.approx(-3.0103, abs=1e-2)
    assert phase_deg[0] == pytest.approx(-45.0, abs=1e-2)


def test_bode_samples_sweep_matches_formula():
    tau = 1000 * 1e-6
    freqs, mag_db, phase_deg = bode_samples(
        "e1,1,0,1:r1,1,2,1000:c1,2,0,1e-6", "v_2",
        f_min=1, f_max=1e6, n=25)
    assert len(freqs) == len(mag_db) == len(phase_deg) == 25
    assert freqs[0] == pytest.approx(1.0)
    assert freqs[-1] == pytest.approx(1e6)
    for f, m, p in zip(freqs, mag_db, phase_deg):
        w = 2 * math.pi * f
        h = 1 / (1 + 1j * w * tau)
        assert m == pytest.approx(20 * math.log10(abs(h)), abs=1e-6)
        assert p == pytest.approx(math.degrees(math.atan2(h.imag, h.real)), abs=1e-6)


def test_bode_samples_rejects_bad_range():
    with pytest.raises(PlotError):
        bode_samples("e1,1,0,1:r1,1,2,1000:c1,2,0,1e-6", "v_2",
                      f_min=0, f_max=100)
    with pytest.raises(PlotError):
        bode_samples("e1,1,0,1:r1,1,2,1000:c1,2,0,1e-6", "v_2",
                      f_min=100, f_max=10)
