"""
transient_example.py

A worked example of Symbulator's transient (time-domain) analysis:
an RC low-pass circuit driven by a 5V step, solved symbolically in the
s-domain with fd() and then inverse-Laplace-transformed back to the
time domain with tr().

Circuit:
    e1: 5V step source, node 1 -> node 0 (ground)
    r1: 1k resistor, node 1 -> node 2
    c1: 1uF capacitor, node 2 -> node 0 (ground)

This is the classic RC charging curve, v_2(t) = 5*(1 - exp(-t/tau))
with tau = R*C = 1 ms.

Run it with:
    python transient_example.py
(from the same folder as the symbulator package, e.g. Downloads\\symbulator_py)
"""

import sympy as sp
from symbulator import fd, tr

DESC = "e1,1,0,5/s:r1,1,2,1000:c1,2,0,1e-6"

print("Circuit:", DESC)
print()

# Step 1: solve in the s-domain (Laplace domain)
res_s = fd(DESC)
print("s-domain node-2 voltage, v_2(s):")
print(" ", res_s.v("2"))
print()

# Step 2: inverse-Laplace-transform back to the time domain
res_t = tr(DESC, variables=["v_2"])
print("time-domain node-2 voltage, v_2(t):")
print(" ", res_t["v_2"])
print()

# Step 3: evaluate at a few time points
t = sp.Symbol("t", positive=True)
tau = 1000 * 1e-6  # R * C = 1 ms
print(f"Time constant tau = R*C = {tau*1000:.1f} ms")
print()
print(f"{'t (ms)':>10} | {'v_2(t) (V)':>12}")
print("-" * 25)
for t_ms in (0, 0.5, 1.0, 2.0, 3.0, 5.0):
    tv = t_ms / 1000
    val = res_t["v_2"].subs(t, tv)
    print(f"{t_ms:>10.1f} | {float(sp.N(val)):>12.4f}")

print()
print("(As expected: 0V at t=0, ~63% of 5V = 3.16V after one time")
print(" constant (t=1ms), and asymptoting toward 5V.)")
