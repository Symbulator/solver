# symbulator (Python port)

A Python/SymPy port of **Symbulator 8**, Roberto Perez-Franco's symbolic
linear-circuit simulator for the TI-Nspire CX II CAS.

All of the original's analysis tools are now ported: DC, AC (phasor),
s-domain (Laplace), and transient analysis; Thevenin/Norton equivalents;
two-port parameter extraction; and the expert-mode dispatcher. See
**Scope** below for the handful of things that are intentionally
simplified relative to the calculator version, and why.

## Install

```
pip install -r requirements.txt
```

## Quick start

```python
from symbulator import dc, ac, fd, tr, th, er, port

# 5V source through a 1k/1k voltage divider
res = dc("e1,1,0,5:r1,1,2,1'k:r2,2,0,1'k")
print(res.v("2"))     # 5/2
print(res.i("r1"))    # 1/400 (2.5 mA)
print(res["p_r1"])    # power dissipated in r1

# Series RLC driven at omega = 1000 rad/s
res = ac("e1,1,0,10:r1,1,2,100:l1,2,3,0.1:c1,3,0,1e-6", omega=1000)
print(res.v("2"))
print(res["z_e1"])    # input impedance seen by the source

# Thevenin equivalent between node 2 and ground
eq = th("e1,1,0,12:r1,1,2,4'k:r2,2,0,2'k", "2", "0", domain="dc")
print(eq.vth, eq.z, eq.pmax)

# Step response of an RC circuit, in the time domain
res = tr("e1,1,0,5/s:r1,1,2,1000:c1,2,0,1e-6", variables=["v_2"])
print(res["v_2"])      # 5*(1 - exp(-1000*t))*Heaviside(t)-style result
```

## Circuit description syntax

Unchanged from the calculator (minus the leading `:`): elements are
separated by `:`, fields within an element by `,`. Node `0` is ground.

| Prefix | Element | Fields |
|---|---|---|
| `r` | resistor | name,n1,n2,value |
| `l` | inductor | name,n1,n2,value[,initial_current] |
| `c` | capacitor | name,n1,n2,value[,initial_voltage] |
| `e` | voltage source (indep. or dependent) | name,n1,n2,value |
| `j` | current source (indep. or dependent) | name,n1,n2,value |
| `o` | ideal op-amp (nullor) | name,n_plus,n_minus,n_out |
| `m` | mutual inductance | name,Lname1,Lname2,M |
| `s` | short circuit | name,n1,n2 |
| `t` | ideal transformer | name,n1,n2,turns1,turns2 |
| `z,y,h,g,a,b` | grounded two-port block | name,n1,n2 (params passed separately, see below) |

The optional initial-condition field on `l`/`c` (initial inductor
current / capacitor voltage) is only meaningful for `fd()`/`tr()`; it's
ignored by `dc()`/`ac()`. Unlike the original -- which required a
different field count per element depending on which analysis tool was
running -- this port always accepts the extra field and just treats it
as 0 if omitted, regardless of which function you call.

**Dependent (controlled) sources** work "for free": a value field can be
any SymPy-parseable expression referencing other node-voltage/current
symbols (`v_<node>`, `i_<element>`), e.g. `e2,3,0,2*v_2` for a VCVS.
This mirrors how the original evaluated value strings through the
calculator's own expression engine.

**Unit shorthand:** the calculator's own `'k`/`'M`/`'u`/... syntax
(`1'k` = 1000) is always unambiguous, as is an explicit product with a
symbol (`1*k`). A *bare* suffix like `1k` could mean either one, so by
default (`suffix="ask"`) it raises `AmbiguousValueError` listing every
such value; pass `suffix="si"` to read them all as SI units, or
`suffix="var"` to read them all as number-times-variable. Use
`find_ambiguous_values(desc)` to scan a description without solving --
that's what the web front end uses to ask the user interactively.

**Two-port parameters** (`z/y/h/g/a/b`) are supplied via a `params`
dict, since on the calculator they were either predefined variables or
entered interactively:

```python
params = {"y1": {"11": "0.001", "12": "-0.001", "21": "-0.001", "22": "0.001"}}
res = dc("e1,1,0,10:y1,1,2:rl,2,0,1'k", params=params)
```

If an element's params are omitted, they're left as free symbols named
`<name>11`, `<name>12`, etc. (matching the original's "leave them
symbolic" default). Use `port()` (below) to go the other way and
*extract* z/y/h/g/a/b parameters from an actual sub-circuit.

## DC / AC / s-domain results

`dc()`, `ac()`, and `fd()` return a `Result` with:
- `res.v(node)` -- node voltage
- `res.i(name)` -- element/branch current
- `res["p_<name>"]` / `res["ap_<name>"]` -- real/apparent power (DC / AC only)
- `res["s_<name>"]` -- complex power (AC only)
- `res["z_<name>"]` / `res["r_<name>"]` -- impedance / resistance seen by a source (AC / DC only)

(The power/impedance derived quantities are DC/AC-only, matching the
original -- `fd()` doesn't compute them either.)

`ac()` takes a `use_rms=True` flag to switch the power convention from
peak-amplitude phasors (default, dividing by 2) to RMS phasors, matching
the original's `userms` setting.

## Thevenin / Norton: `th()` and `er()`

```python
eq = th("e1,1,0,12:r1,1,2,4'k:r2,2,0,2'k", n1="2", n2="0", domain="dc")
eq.vth    # open-circuit (Thevenin) voltage
eq.ino    # short-circuit (Norton) current
eq.z      # Req (dc) or Zeq (ac) = vth/ino
eq.pmax   # max power transferable to a matched load
```

`th()` is for **active** circuits (ones with their own independent
sources) -- it raises if the open-circuit voltage comes out to 0, same
as the original's redirect message. For a **passive** (source-free)
network, use `er()` instead, which injects a single 1A test current and
reads the equivalent resistance/impedance directly:

```python
req = er("r1,1,2,1'k:r2,2,0,2'k", n1="1", n2="0", domain="dc")  # 3000
```

## Two-port extraction: `port()`

Extracts z/y/h/g/a/b parameters of a whole circuit between two grounded
ports (the inverse of feeding pre-defined parameters into a `z`/`y`/...
circuit *element*, described above):

```python
params = port("r1,1,3,100:r2,2,3,200:r3,3,0,50", n1="1", n2="2", kind="z", domain="dc")
params["11"], params["12"], params["21"], params["22"]
```

Works the same way in AC (pass `omega=...` and `domain="ac"`).

## s-domain and transient: `fd()` and `tr()`

```python
from symbulator import fd, tr, t2s, s2t

# Step response of an RC low-pass, starting from rest
res_s = fd("e1,1,0,5/s:r1,1,2,1000:c1,2,0,1e-6")   # s-domain answer
res_t = tr("e1,1,0,5/s:r1,1,2,1000:c1,2,0,1e-6")    # inverse-Laplace'd to time domain
res_t["v_2"]

# Natural response of a discharging inductor with an initial condition
res_t = tr("l1,0,2,0.2,3:r1,2,0,100", variables=["i_l1"])  # I0=3A, L=0.2H, R=100 ohm
res_t["i_l1"]   # 3*exp(-500*t)
```

`t2s()`/`s2t()` wrap SymPy's `laplace_transform`/`inverse_laplace_transform`
directly, for preparing a time-domain source value or hand-checking an
answer.

`tr(desc, variables=[...])` lets you limit which answers get
inverse-Laplace-transformed -- useful since that step can be slow (or
fail to find a closed form) for complicated expressions; omit
`variables` to attempt every solved node voltage and element current.
Any individual variable that can't be transformed is silently left out
of the result rather than failing the whole call.

**Simplification vs. the original:** the original auto-detected when a
source's value was a function of time and Laplace-transformed it for
you (and called out to a separate `lf\\ilaplace`/`lf\\laplace` calculator
library for the actual transform, which wasn't included in the document
this was ported from). This port skips the auto-detection: give `fd()`
source values already in the s-domain (e.g. `"5/s"` for a 5V step,
`"1"` for an impulse), using `t2s()` first if you're starting from a
time-domain expression. `tr()` then uses SymPy's own
`inverse_laplace_transform` for the reverse step, per your call on how
to handle the missing library.

## Expert mode: `ex()`

A single dispatcher over `dc`/`ac`/`fd`/`tr`, for callers that want to
pick the analysis type dynamically rather than calling a specific
function -- ports `ex()`. On the calculator this interactively asked
"1:DC 2:AC 3:FD 4:TR"; as a library there's no prompt to answer, so
`domain` is just a normal argument (the word, or the calculator's own
1-4 shorthand):

```python
ex("e1,1,0,5:r1,1,2,1'k:r2,2,0,1'k", domain="dc")
ex("e1,1,0,5:r1,1,0,100", domain="ac", omega=1000)   # omega required for ac
ex("l1,0,2,0.2,3:r1,2,0,100", domain="tr", variables=["i_l1"])
```

Expert mode's "Add equations / Add unknowns / Add conditions" prompts
are ported as keyword arguments, available on `ex()` and on
`dc`/`ac`/`fd`/`tr` directly:

```python
# Design problem: what r_b makes the divider output exactly 6 V?
res = dc("e1,1,0,12:r1,1,2,4'k:r2,2,0,r_b",
         equations=["v_2 = 6"], unknowns=["r_b"])
res.values["r_b"]        # 4000

# Derived quantity: a new symbol in an equation is auto-added as an
# unknown, so no unknowns list is needed for this style.
res = dc("e1,1,0,12:r1,1,2,4'k:r2,2,0,2'k", equations=["pout = v_2*i_r2"])

# Conditions -- the TI's "|" (with) operator: substitutions applied to
# the whole system at solve time.
res = dc("e1,1,0,vin:r1,1,2,r_a:r2,2,0,r_b",
         conditions=["vin = 12", "r_a = 4'k", "r_b = 2'k"])
```

Extra equations run through the same unit-prefix expander as circuit
values (so `6*4'k` works), and accept either `lhs = rhs` strings or a
bare expression (treated as `expr = 0`). A symbolic *component value*
you want solved (like `r_b` above) must be listed in `unknowns` -- the
solver otherwise treats it as a fixed parameter, matching the
original's separate "Add unknowns" prompt.

## Scope: what's simplified vs. the calculator version

- **`pf()`** is ported as a simplified, explicit-argument version (pass
  a voltage and current phasor directly); the original's implicit
  per-element-type sign convention, driven by reading calculator
  variables like `v<name>`/`i<name>` automatically, wasn't replicated.
- **`fd()`/`tr()`** require s-domain source values up front rather than
  auto-detecting and transforming time-domain ones (see above).
- **No interactive prompts anywhere** -- everything the calculator asked
  for via `RequestStr` (analysis type, which answers to save, expert-mode
  custom equations, two-port parameter values, etc.) is a plain function
  argument here instead.
- **No `Disp` progress narration** -- the calculator printed step-by-step
  status messages during a simulation; this port just returns the
  answer.

## Tests

```
pytest symbulator/tests/ -v
```

48 tests across six files:
- `test_circuits.py` (21): DC/AC voltage & current dividers, series RLC
  impedance, inverting/non-inverting op-amp gain, a voltage-controlled
  voltage source, an ideal transformer, mutual inductance (with and
  without coupling), a two-port block, derived power quantities,
  zero-valued-capacitor handling, and parser error handling.
- `test_equiv.py` (9): Thevenin voltage/impedance and its cross-check
  against directly solving with a load attached, `er()` on series/parallel
  passive networks, `port()` z/y/a-parameter extraction (including a
  z·y matrix-inverse consistency check and an a-parameter round trip
  through the Phase 1 two-port element), and an AC two-port case.
- `test_laplace.py` (5): `t2s`/`s2t` round trips, an RC step response
  checked numerically against the closed-form exponential, an RL natural
  response with a nonzero initial condition checked against its
  closed-form solution, and zero-valued-capacitor handling carried
  into `fd()`.
- `test_dispatch.py` (6): `ex()` dispatch to each of the four analysis
  modes, its numeric-shorthand domain aliases, and its error handling.
- `test_expert.py` (7): expert-mode extras -- solving for a symbolic
  component via an added equation + unknown, auto-added derived-quantity
  symbols, unit shorthand inside added equations, conditions as
  solve-time substitutions, and error handling.
