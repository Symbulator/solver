# Fact-check of the draft JOSS paper

**Draft checked:** `C:\Users\perez\Downloads\paper.md` and `paper.bib` (dated in its
front matter 1 October 2026). The brief named `paper/paper.md` in this repository;
no such file exists here, in the repository's history, or on either branch
(`main`, `sch-relax`), so the Downloads copy is the one checked.

**Code checked:** `C:\Users\perez\Claude Symbulator\Application\v9\repos\solver`,
branch `main`, commit `220ff2c` (= `origin/main`), package version **0.6.17**,
Python 3.14.7, SymPy 1.14.0. Checked 1 October 2026.

**Method:** every claim was run, not read, where that was possible. The scripts are
reproduced inline below; each output block is what the command printed. Nothing
in the code, tests or packaging was modified. `paper.md` was not edited — all
proposed wording is in this report.

Verdicts: **confirmed**, **wrong**, **partly**, **cannot verify**.

## Status, 1 October 2026: fixes applied (#470, #471)

This report is kept as written, with two sections amended where Roberto ruled
(2a and 4c, each marked). After it, at his word:

- **The paper** is now in this repository, `paper/paper.md` and `paper/paper.bib`,
  with every fix in *Prioritised fixes* below applied. The Downloads copy is
  left untouched as the original draft. Every code claim in the corrected paper
  was run again (the divider, `5/2`, the inverse example's `r_b = 1000`, the
  polar float, `tr`/`fd` sources and `{5}`, `conditions=`, the answer keys in all
  four analyses, the local reference and the floating refusal). The two new
  references, the 2001 thesis and the *BURAN* article, were read from the
  archive's primary sources. The article names **fourteen** countries, so the
  paper says fourteen; the archive catalogue's "seventeen" is not supported by
  the article's own text.
- **The repository:** the README's test section rewritten (a command, not a
  count; the ahkab and IPython skips explained), the two stale "reported
  floating" sentences corrected, the quick start's transient made exact
  (`1'u`), Python versions and extras stated; `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, `CITATION.cff` and a GitHub Actions workflow on Python
  3.9 to 3.14 added; `notebooks/README.md` now describes `books/`; the release
  tagged.
- **Beta:** Roberto ruled that versions 9 and 8 leave beta (#471). The
  classifier is now `5 - Production/Stable`, and the β is gone from every
  wordmark (app, learn, landing page), as are the landing page's beta wording and
  version 8's Beta chip and caveat. The live sites carry it; PyPI's page takes
  the classifier and the README at the next release.

---

## 1. Formulation — **wrong**

> *The solver writes Kirchhoff's current law at each node together with a
> constitutive equation for every element, keeping every branch voltage and
> current as an unknown. This is larger than modified nodal analysis and closer
> to the sparse tableau approach.*

### What the engine does

`symbulator/engine.py`, class `Circuit`, `stamp_all()` and the `_stamp_<kind>`
methods (lines 308–760), then `sp.solve(circuit.equations, unknowns, dict=True)`
in `solve_circuit_all` (line ~1149). No matrix is assembled; a list of `sp.Eq`
is handed to `sympy.solve`.

| Element | Unknowns it adds | Equation it adds |
|---|---|---|
| node (non-reference) | `v_<node>` | KCL, once all elements are stamped |
| `r` resistor | `i_<r>` | `v(n1) - v(n2) = R·i` |
| `l` inductor | `i_<l>` | DC `v(n1)=v(n2)`; AC `= jωL·i (+ jωM·i_other)`; FD `(v1-v2)/s = L(i - i0/s) + …` |
| `e` voltage source | `i_<e>` | `v(n1) - v(n2) = value` |
| `s` short, and any 0-valued r/l/e | `i_<name>` | `v(n1) = v(n2)` |
| `o` op-amp | `i_<o>` (output) | `v(+) = v(−)` |
| `t` transformer | one current per live terminal | voltage ratio + current ratio |
| two-port `z/y/h/g/a/b` | one current per live terminal | its two port relations |
| `c` capacitor | **none** | **none**: `i = sC(v1-v2) - C·v0` (or `jωC…`) is substituted into KCL |
| `j` current source | **none** | **none**: its value is added into KCL directly |

**No element voltage is ever an unknown.** `v_r1`, `p_r1`, `r_e1` and so on are
computed *after* the solve by `analysis._derived()`, from the node voltages and
currents, and only in DC and AC (`analysis.py` line ~393). In FD and TR they are
not produced at all.

### Evidence (printed systems)

Script: build `Circuit(parse_circuit(desc), domain, suffix="si")`, call
`stamp_all()`, print `unknowns`, `equations` and `known`.

```
Voltage divider [dc]   e1,1,0,5:r1,1,2,1000:r2,2,0,1000
unknowns (5): ['i_e1', 'v_1', 'i_r1', 'v_2', 'i_r2']
equations (5):
    v_1 = 5
    v_1 - v_2 = 1000*i_r1
    v_2 = 1000*i_r2
    i_e1 + i_r1 = 0
    -i_r1 + i_r2 = 0

RC with current source, AC   j1,0,1,2:r1,1,0,10:c1,1,0,0.01   (omega=100)
unknowns (2): ['v_1', 'i_r1']
equations (2):
    v_1 = 10*i_r1
    i_r1 + 1.0*I*v_1 - 2 = 0
known (eliminated) currents: {'i_j1': '2', 'i_c1': '1.0*I*v_1'}

Inverting op-amp + VCVS + CCCS [dc]
  e1,1,0,1:r1,1,2,1000:r2,2,3,4000:o1,0,2,3:e2,4,0,2*v_3:r3,4,5,100:j1,5,0,0.5*i_r3:r4,5,0,50
unknowns (12): ['i_e1','v_1','i_r1','v_2','i_r2','v_3','i_o1','i_e2','v_4','i_r3','v_5','i_r4']
equations (12):
    v_1 = 1
    v_1 - v_2 = 1000*i_r1
    v_2 - v_3 = 4000*i_r2
    0 = v_2                      # op-amp: v(+) = v(−), + grounded
    v_4 = 2*v_3                  # VCVS
    v_4 - v_5 = 100*i_r3
    v_5 = 50*i_r4
    i_e1 + i_r1 = 0              # KCL node 1
    -i_r1 + i_r2 = 0             # KCL node 2
    -i_o1 - i_r2 = 0             # KCL node 3
    i_e2 + i_r3 = 0              # KCL node 4
    -0.5*i_r3 + i_r4 = 0         # KCL node 5, CCCS folded in
known (eliminated) currents: {'i_j1': '0.5*i_r3'}

RL with initial current, FD   e1,1,0,5/s:r1,1,2,2:l1,2,0,1,3
unknowns (5): ['i_e1', 'v_1', 'i_r1', 'v_2', 'i_l1']
    v_2/s = i_l1 - 3/s   …

Ideal transformer [dc]   e1,1,0,10:r1,1,2,1:t1,2,3,1,2:r2,3,0,4
unknowns: ['i_e1','v_1','i_r1','v_2','i_t12','v_3','i_t13','i_r2']
    Eq(v_2, v_3/2)   Eq(i_t13, -i_t12/2)   + KCL …
```

For comparison: the textbook sparse tableau (Hachtel et al. 1971) of the divider has
node voltages **and** 3 branch voltages **and** 3 branch currents, i.e. 8 unknowns.
The engine has 5, with no branch voltages. Classical MNA (Ho et al. 1975, resistors
in "group 1") has 3: `v_1`, `v_2`, `i_e1`.

### Verdict

Not sparse tableau. It is a **modified nodal formulation in which the current of
every resistor, inductor, voltage source, short, op-amp output, transformer and
two-port terminal is kept as an unknown**. In Ho–Ruehli–Brennan's own terms, those
elements are placed in "group 2" (current retained) and capacitors and current
sources in "group 1" (current eliminated into KCL). It is larger than minimal MNA,
but only by one unknown per resistor or inductor. It has no branch-voltage unknowns.

It is worth knowing that this is what Roberto's 1999 competition paper chose *against*
MNA under the name **equation generation**, a method he learned from Joe Riel's
Maple-based simulator Syrup (`Documentation/paper/references/1999_paper_english_translation.html`,
section "Analysis method selection"). Its stated reasons were the ease of dependent
sources, transformers and two-ports, and the avoidance of symbolic matrix
manipulation. The Python engine keeps that design: equations as a list, solved by
`sympy.solve`, with no matrix.

The draft's pedagogical claim also fails on its own terms. *"Every quantity a student
might be asked for is already a named unknown, and derived quantities (power, source
impedance) follow without post-processing"* is false: voltage drops, powers and
source impedances are produced by `_derived()` after the solve, and only in DC and AC.

### Proposed wording

> **Formulation.** The solver generates the circuit's equations directly and hands
> them, as a list, to SymPy's `solve`; no matrix is assembled. It writes Kirchhoff's
> current law at every non-reference node and one defining equation for each element
> that carries its own current: resistors, inductors, voltage sources, shorts, op-amp
> outputs, transformer windings and two-port terminals. The unknowns are the node
> voltages and those element currents. Capacitor and current-source currents are
> written directly in terms of node voltages and substituted into KCL. In the terms of
> modified nodal analysis [@ho1975] this puts most elements in the "group 2" whose
> currents are retained, giving a system somewhat larger than minimal MNA but with no
> branch-voltage unknowns, unlike sparse tableau [@hachtel1971]. Keeping element
> currents as named unknowns lets a dependent source, an added equation or a condition
> refer to `i_r1` directly, which is what makes controlled sources and inverse problems
> use the same mechanism. Voltage drops, powers and the impedance each source sees are
> computed from the solution afterwards, in DC and AC. The design, called *equation
> generation*, dates from the 1999 calculator version, where it was chosen over nodal
> matrix methods for its handling of dependent sources, transformers and two-ports in
> symbolic form. It suits the small and medium circuits of teaching and design
> derivations, not large netlists.

(Whether to keep the Syrup/Joe Riel attribution is Roberto's call. It is in his own
1999 text.)

---

## 2. Summary and Software design claims

### 2a. Exact rationals by default — **partly**

```python
dc("e1,1,0,5:r1,1,2,1'k:r2,2,0,1'k")
#  v_2 = 5/2 (Rational), i_r1 = 1/400, p_r1 = 1/160
dc("e1,1,0,vin:r1,1,2,ra:r2,2,0,rb").values["v_2"]
#  rb*vin/(ra + rb)          <- the Summary's example, exactly
dc("e1,1,0,5:r1,1,2,2.5:r2,2,0,2.5").values["v_2"]
#  2.50000000000000 (Float)  <- float only because the user wrote one
```

Confirmed for everything above. **But "floating point enters only where the user
writes it" is false for phasors in polar form**, a notation the paper's own audience
uses constantly:

```python
ac('e1,1,0,(10∠0°):r1,1,0,1',  omega=1).values['i_r1']  # 10.0000000000000
ac('e1,1,0,(10∠90°):r1,1,0,1', omega=1).values['i_r1']  # 10.0*I
ac('e1,1,0,(10∠45°):r1,1,0,1', omega=1).values['i_r1']  # 7.07106781186548 + 7.07106781186548*I
ac('e1,1,0,10*exp(I*pi/4):r1,1,0,1', omega=1)...        # 10*(-1)**(1/4)   (exact)
```

All inputs are integers, but the `∠` form is evaluated numerically.

**This is a design decision, not a defect** (amended 1 Oct 2026). Roberto ruled on
25 Aug 2026, recorded at `symbulator/si_prefix.py` line 208, that a polar phasor
becomes a rectangular floating-point number: SymPy cannot reduce
`exp(I*pi*130/180)` to closed form, so the exact form is carried unevaluated
through every equation. Alexander & Sadiku's Example 12.12 had not finished after
25 seconds that way, against about one second with rectangular sources. *"A phasor
angle is a measurement, and the alternative is circuits that do not solve."* On
1 Oct 2026 he confirmed it: making polars exact is not practical. The fix is to
the paper's wording only.

**Proposed wording (applied):** *"Inputs are parsed as exact rationals where
possible, so a 5 V source across two 1 kΩ resistors gives `5/2`, not `2.5`. A
decimal the user types stays a floating-point number. A phasor written in polar
form, such as `(120∠30°)`, is deliberately converted to a rectangular
floating-point number: an angle that SymPy cannot reduce to closed form would
otherwise be carried unevaluated through every equation…"*

### 2b. `tr()` reads a constant as a step, `fd()` as-is in s — **confirmed**

```python
tr("e1,1,0,5:r1,1,0,1").values["v_1"]            # 5   (t ≥ 0)
tr("e1,1,0,5:r1,1,2,1:c1,2,0,1").values["v_2"]   # 5 - 5*exp(-t)   <- step response
fd("e1,1,0,5:r1,1,0,1").values["v_1"]            # 5   -> s2t: 5*DiracDelta(t)
fd("e1,1,0,{5}:r1,1,0,1").values["v_1"]          # 5/s <- the {...} time-domain escape
```

The paper's sentence is right. It could mention the `{…}` escape, since that is how a
reader writes a time-domain value in `fd()`.

### 2c. Bare `1k` raises `AmbiguousValueError`; `1'k` does not — **confirmed**

```
dc("e1,1,0,5:r1,1,0,1k")
  -> AmbiguousValueError: Ambiguous value(s): '1k' in r1. Write the SI-unit meaning
     explicitly with an apostrophe (e.g. 1'k = 1000) or the variable meaning with a
     star (e.g. 1*k), or pass suffix='si' / suffix='var' to choose for all of them.
dc("e1,1,0,5:r1,1,0,1k:r2,1,0,4.7m")
  -> Ambiguous value(s): '1k' in r1, '4.7m' in r2. …     <- "listing every" value: yes
dc("e1,1,0,5:r1,1,0,1'k").values["i_r1"]              -> 1/200
dc(..., suffix="si") -> 1/200 ;  dc(..., suffix="var") -> 5/k
```

### 2d. Isolated sections get a local reference and a note — **confirmed** (with one README contradiction)

```python
# transformer, floating secondary
r = dc("e,1,0,10:r0,1,2,1:t,[2,0],[3,5],[2,1]:rl,3,5,100")
r.references  # {'5': ['3']}
r.notes       # ['Node(s) 5, 3 have no path to node 0 (they lie behind a port or a
              #   coupling), so their voltages are measured against 5, taken as 0.']
r.values['v_5'] # 0 ;  v_3 = 2000/401, i_rl = 20/401 …

# two four-terminal z blocks (README's own example)
dc("za,[p,0],[q,m],[25,20,5,10]:zb,[p,0],[m,n],[50,25,25,30]:e1,p,0,1").references
              # {'m': ['q', 'n']}  + the same note

# mutual inductance (AC)
ac("e1,1,0,10:r1,1,2,1:l1,2,0,1:l2,3,4,1:m1,l1,l2,0.5:r2,3,4,1", omega=1).references
              # {'4': ['3']}  + the same note

# a dangling piece with no port is still an error
dc("e1,1,0,10:r1,1,0,1:r2,3,4,4")
  -> CircuitError: Node(s) 3, 4 have no path to the reference node 0; that part of
     the circuit is floating and its voltages are undefined.
```

**Proposed wording** (mutual inductance is covered too, and the contrast with a truly
floating piece is worth stating): *"Circuit sections connected to the rest only
through a transformer, a two-port block or a mutual inductance are given an explicit
local reference, and the result says which node was chosen; a section with no
connection at all is refused as floating."*

**README defect found in passing:** `README.md` line ~148 still says *"a side of the
circuit with no path to node 0 is reported floating (code 217)"*, and the comment
above the first four-terminal example says the secondary *"must have its own path to
ground (here r5), or it is reported floating"*. Both contradict the README's own later
section (line ~237) and the behaviour above. A reviewer reading the README will see
the contradiction.

### 2e. `equations=` / `unknowns=` / `conditions=` join the circuit's own system — **confirmed**

```python
dc("e1,1,0,12:r1,1,2,1'k:r2,2,0,r_b", equations=["v_2 = 6"], unknowns=["r_b"])
#  r_b = 1000, v_2 = 6, i_r1 = 3/500, p_r2 = 9/250 …
# the stamped circuit alone: 5 equations, unknowns i_e1, v_1, i_r1, v_2, i_r2;
# engine.solve_circuit_all appends the parsed extra equation and r_b, then one sp.solve.
dc("e1,1,0,vin:r1,1,2,ra:r2,2,0,rb", conditions=["ra = 1000", "rb = 3000"]).values["v_2"]
#  3*vin/4
```

One precision for the text: `conditions=` are **substitutions** applied at solve time
(the calculator's `|`), not equations. The paper's sentence lumps all three as
"appended to the circuit's own equation set". Suggested: *"Extra equations and
unknowns (`equations=`, `unknowns=`) join the circuit's own equation set before
solving, and `conditions=` substitute values into it, the calculator's `|` operator,
so design questions and analysis questions use one mechanism."*

### 2f. Cell magics `%%dc`, `%%ac`, `%%fd`, `%%tr` — **confirmed**

Run through a real `IPython.core.interactiveshell.InteractiveShell` (IPython 9.17.1):

```
%load_ext symbulator
registered cell magics: ['ac', 'dc', 'fd', 'tr']
%%dc            (e1,1,0,5 / r1,1,2,1'k / r2,2,0,1'k)   success=True  v_2=5/2
%%ac omega=1000 (e1,1,0,10 / r1,1,2,1'k / c1,2,0,1'u)  success=True  v_2=5 - 5*I
%%fd            (e1,1,0,5/s / r1,1,2,1 / c1,2,0,1)     success=True  v_2=5/(s*(s + 1))
%%tr            (e1,1,0,5 / r1,1,2,1 / c1,2,0,1)       success=True  v_2=5 - 5*exp(-t)
```

Each also displays the schematic (an SVG) before the result.

### 2g. Calculator descriptions run unchanged — **partly**

Test corpus: every circuit description quoted in the 2023 hand-written Symbulator 7 and 8
documentation (`Documentation/originals/docs-page7.html`, `docs-page8.html`), extracted
by regex at an opening quote and run unchanged through `find_ambiguous_values`,
`parse_circuit`, then `dc()`, `ac(omega=1)` and `fd()` in turn.

```
docs-page8.html: 109 unique descriptions, as printed
     82  parsed and solved (dc/ac/fd)
     27  no plain solve
```

Every one of the 27 failures is one of these:

1. **The Nspire's display characters.** The pages print what the calculator displays:
   the imaginary unit as `𝐢` (U+1D422), minus as an en dash `–` (U+2013), and `√`.
   All three are refused (`UnsafeExpressionError: invalid character '–' (U+2013)`).
   These are also what a user gets when copying text out of a `.tns` document.
2. **Implicit multiplication with the imaginary unit first:** `-𝐢5.`, `10.+𝐢5.`,
   `.4+𝐢.3`. With `𝐢`→`i` substituted, these still fail (`'10.+i5.': invalid syntax`),
   because `i5` reads as a name. `5.𝐢`, `8-6i`, `4.+2.i`, `-i*5.`, `2vr1` and `.2vr1`
   all work.
3. **A calculator library call:** `e,1,0,s\t2s(u(t))` (the `lf\t2s` Laplace library).
   The package's equivalent is `{u(t)}`.

After mapping only the three glyphs to ASCII (`𝐢`→`i`, `–`→`-`, `√`→`sqrt`):

```
docs-page7.html: 109 unique   91 solved   17 no plain solve   1 parse error
docs-page8.html: 109 unique   88 solved   21 no plain solve
```

Nearly all the remaining failures are the `i`-first implicit products, plus the `lf\`
call. The mutual-inductance-as-impedance entries fail only on `i5.`-style values. The
one parse error on page 7 is an extraction artefact: the regex cut the description
before its ground node.

Direct probes of features the calculator had:

```
OK   :e1,1,0,5:r1,1,2,1'k:r2,2,0,1'k   (leading colon accepted)
OK   E1,1,0,5:R1,1,0,2                 (names fold to lower case)
OK   e,1,0,(200∠45°):r1,1,0,4          (polar source; float result, see 2a)
OK   r1,1,0,[2,2]  and  10+[4i,8-6i]   (parallel-resistor brackets)
OK   2vr1, .2vr1                       (implicit products, calculator style)
ERR  r1,1,0,1k            -> AmbiguousValueError (by design, 2c)
ERR  r-x,1,0,2            -> element names must be identifiers (#159)
ERR  e1,1,0,[5]           -> brackets outside r values and two-port params (#165)
```

Documented exceptions (README "Scope" and CHANGELOG): the bare-suffix rule; the
initial-condition field always optional (a superset, harmless); no interactive
prompts, since every prompt is a function argument; and TR before 0.5.5 (history
only).

**Proposed wording** (Summary, last sentence): *"Circuits are written in the same
compact notation the calculator versions used, so descriptions written for them run
with few or no changes. The exceptions are a bare unit suffix such as `1k`, which must
be written `1'k`, and text copied from the calculator's display, whose imaginary-unit
and minus glyphs must be typed as `i` (or `j`) and `-`."* The same softening applies to
"Continuity" in *Statement of need* ("without rewriting them" → "with little or no
rewriting") and to "preserves compatibility with 25 years of user material" in
*Software design*.

---

## 3. Claims about the wider project

These can be partly checked from the sibling repositories on this machine
(`Application/v9/repos/server`, `repos/local`), but **not from the solver repository
alone**. A JOSS reviewer sees only the solver repository.

### 3a. Core of the web app and of the EqSheet tool — **partly (app: confirmed; EqSheet: wrong; URL: wrong)**

- **Web app, confirmed.** `repos/server/requirements.txt` pins `symbulator>=0.6.16`.
  `app.py` and `symbulator_ui.py` import `symbulator` throughout (`from symbulator
  import ex, tr, th, er, port`, `symbulator.engine.Circuit`, `symbulator.laplace`…).
  The offline builds bundle `symbulator-0.6.17-py3-none-any.whl` (`build_local.py`,
  `WHEEL =`).
- **EqSheet (the Numerical Solver), wrong.** `repos/server/eqsheet.py` imports only
  `sympy` and `scipy`; the numerical solve is `scipy.optimize.root`/`least_squares`.
  The offline build deliberately does **not** load the symbulator wheel for it
  (`build_local.py` line ~899: *"it loads scipy and *not* the symbulator wheel"*). The
  package's only role there is on the app's side, building the equations that are
  handed over.
- **The web app is not "at symbulator.com".** `symbulator.com` is the landing page.
  The app is at `symbulator.pythonanywhere.com` and `install.symbulator.com`.
- **"…and of its documentation at learn.symbulator.com"** (*Research impact*) is
  overstated. The documentation is static PHP/HTML. Its build imports the app tree to
  check the Manual's circuits, but no page calls the package.

**Proposed wording:** *"The same core runs the Symbulator web application
(symbulator.pythonanywhere.com, and an offline build that runs in the browser through
Pyodide), where it also writes the equation systems handed to the app's numerical
equation-sheet tool; the package also provides Jupyter cell magics (`%%dc`, `%%ac`,
`%%fd`, `%%tr`) and is usable from any script."*

### 3b. Executed notebooks comparing with the app — **partly**; editions: **the bib is wrong for Nilsson & Riedel**

```
notebooks/books/*.ipynb (24) + quickstart.ipynb + the_monograph.ipynb
Every notebook: all code cells executed, 0 error outputs, a Colab link present.
  Alexander_Sadiku.ipynb  119 cells  "Problems from Alexander & Sadiku 7ed" (57 entries)
  Nilsson_Riedel.ipynb    109 cells  "Problems from Nilsson & Riedel 12ed"  (50 entries)
  Lesson_01 … Lesson_13 (18 notebooks), Manual, Showcase, Bakers_Dozen, The_Monograph
```

- **Editions:** Alexander & Sadiku **7th** (the bib's `alexander2021`, 7th ed.,
  McGraw-Hill, 2021: consistent). Nilsson & Riedel **12th**; the bib's `nilsson2019`
  is the **11th** edition (2019) and must change to the 12th (Pearson; check the
  year on the title page — the 12th is 2023/©2024). The `TODO(Roberto)` in the bib
  is exactly this.
- **"Comparing the package's answers with those of the web application answer by
  answer."** The notebooks themselves contain no comparison; they run the package.
  The comparison is `notebooks/check_books.py`, which posts each entry through the
  app's own `/api/solve` and needs `repos/server` beside the solver, so a reviewer
  cannot run it. Run today:
  ```
  python notebooks/check_books.py Alexander_Sadiku Nilsson_Riedel Lesson_01
  Alexander_Sadiku: 57 entries, 0 problem(s)
  Lesson_01: 19 entries, 0 problem(s)
  Nilsson_Riedel: 50 entries, 0 problem(s)
  126 entries, 2449 answers and 16 Evaluate/Solve cards compared, 0 problem(s)
  ```
  So the claim holds for these three books, provided the paper says the comparison is
  a script and not something in the notebooks.
- **"Reproduce the worked problems of the Symbulator tutorial and samplers of problems
  from two standard textbooks."** Confirmed in substance: the Lesson notebooks are the
  tutorial's example books. `notebooks/README.md` is stale, though: it lists only
  `quickstart.ipynb` and `the_monograph.ipynb` and does not mention `books/`.

**Proposed wording:** *"The repository includes executed notebooks, each opening in
Google Colab, that run every worked problem of the Symbulator tutorial and two
samplers of problems from standard textbooks [@alexander2021; @nilsson2023]. A
separate script checks each notebook's answers against the web application's, entry
by entry."*

---

## 4. Other issues a JOSS reviewer would flag

### 4a. Test count — README **wrong**

```
python -m pytest -q          (this machine's interpreter, ahkab installed)
576 passed, 2 skipped in 74.05s          26 test files in symbulator/tests/

clean venv, pip install ".[test]", python -m pytest --pyargs symbulator.tests
547 passed, 4 skipped in 62.87s
  SKIPPED test_spice_groundtruth.py:74   ahkab is not available on this toolchain
  SKIPPED test_notebook.py:203           could not import 'IPython'
  SKIPPED [2] test_schematic.py:1026     no op-amp here may be raised
```

The README's *"48 tests across six files"* lists five files, and both numbers are stale
by an order of magnitude: there are **578 tests in 26 files**. In a clean install, the
27 ahkab ground-truth tests are skipped as one module, because ahkab (GPLv2) is
deliberately not in the `test` extra. The README should say so, since that is the one
test that catches symmetric sign errors, and a reviewer running the suite won't
see it run. The IPython-dependent test is skipped too, because the `test` extra
omits IPython.

**Proposed README wording:** *"578 tests across 26 files (`pytest symbulator/tests`).
The 27 SPICE ground-truth tests need `ahkab`, which is GPL-licensed and therefore not
in the `test` extra; install it separately to run them. The notebook tests need
IPython."* Better still, name the command that counts them rather than the number.

### 4b. Versions — **README partly out of date; no mismatch in the packaging**

- `pyproject.toml`: `dynamic = ["version"]`, read from `symbulator.__version__` =
  **0.6.17**.
- PyPI: latest **0.6.17** (60 releases), fetched from `pypi.org/pypi/symbulator/json`.
  The brief's "PyPI's latest is 0.5.26" is out of date by a month.
- CHANGELOG head: `## 0.6.17 -- 20 Sep 2026`. All three agree.
- The README's mentions of 0.5.27 and 0.6.8 are historical ("since 0.5.27", "until
  0.6.8"), not claims about the current version, so they are consistent.
- **Classifiers list Python 3.9–3.12** and `requires-python = ">=3.9"`, but the suite
  was run here only on **3.14** (the only interpreter on this machine), and there is no
  CI to run other versions. Either test 3.9–3.13 or narrow the claim.
- **README quick start drift:** it documents `5 - 5*exp(-1000*t)`; a clean install
  prints `5.0 - 5.0*exp(-1000.0*t)` (the example's `1e-6` is a float). Writing
  `1'u` would make the comment true.

### 4c. "4 - Beta" versus "5 - Production/Stable" and a 1.0 — **premature, for these reasons**

- **The public history is six weeks long.** First commit 21 Aug 2026, 116 commits, all
  authored as `Symbulator`. JOSS asks for evidence of sustained development, and a
  six-week public history is below what reviewers usually expect.
- **The pace of behavioural change.** 60 PyPI releases between 13 Aug and 20 Sep 2026
  (first and last upload times from PyPI's JSON), about five and a half weeks; 0.6.10
  added AC `p`, and 0.6.11 withdrew it at the author's word. Answer names changing
  between minor versions is a beta signal.
- **The app itself is labelled beta.** Open item #137 exists to remove the β from the
  wordmarks "when version 9 leaves beta".
- **Known limitations** (by design, but a "Stable" label invites the question):
  linear circuits only; no voltage drops or powers stored in FD/TR (the author's
  ruling of 20 Sep 2026); polar phasors come back as floats (2a); the schematic drawer
  calls itself a prototype (`schematic.py`, `# LIMITATIONS (prototype)` at line 4919);
  the SPICE translator's own wording was still settling in September; the
  `sch-relax` branch is unmerged. (Corrected 1 Oct 2026: the app's SPICE card has
  carried no beta note since #340, 9 Sep 2026.)
- **No `TODO`/`FIXME`/`XXX`** markers in the package source, and no `xfail` tests. That
  is good and can be said.

Recommendation: keep **4 - Beta** for the JOSS submission.

**Overruled, 1 Oct 2026.** Roberto ruled that version 9 (and version 8) leave
beta, everywhere: solver, interface and documentation (#471). The classifier is
now `5 - Production/Stable`. The points above remain true as facts and are
worth being ready for in review, the short public history above all.

### 4d. Repository hygiene

| Item | Present? | Evidence |
|---|---|---|
| `CONTRIBUTING.md` | **no** | not in tree; GitHub community profile `contributing: null` |
| CI workflow | **no** | no `.github/`; GitHub API `actions/workflows` → `total_count: 0` |
| Git tags / GitHub releases | **no** | `git tag` → 0; API `tags` → `[]`, `releases` → `[]` (60 PyPI releases, none tagged) |
| `CITATION.cff` | **no** | not in tree |
| Code of conduct | **no** | not in tree; community profile `code_of_conduct: null`, health 42% |
| Issue / PR templates | no | community profile |
| `LICENSE` | yes | MIT |
| Install from a clean venv, PyPI | **works** | `python -m venv …; pip install symbulator` → symbulator 0.6.17, sympy 1.14.0, mpmath 1.3.0; README quick start runs (outputs above) |
| Install from a clean venv, checkout | **works** | `pip install ".[test]"` then pytest: 547 passed, 4 skipped |

JOSS's review checklist asks for community guidelines (contributing, reporting issues,
getting support) and for automated tests. Tests exist, but with no CI and no tags a
reviewer cannot tie the archived version to a tested commit. Expect requests for
`CONTRIBUTING.md`, a CI workflow, a tagged release matching the Zenodo archive, and
`CITATION.cff`.

### 4e. Other inaccuracies and overstatements in the paper

1. **AI disclosure is incomplete.** The commit trailers in this repository read:
   ```
   git log --format="%(trailers:key=Co-Authored-By,valueonly)" | sort | uniq -c
     54 Claude Opus 5
     26 Claude Fable 5
     21 Claude Fable 5.1
      9 Claude Sonnet 5
   ```
   The paper lists Sonnet 5, Opus 5 and Fable 5, and omits **Fable 5.1** (21 commits).
   Also, all 116 commits have the author name `Symbulator`, so the history cannot show
   the human's part. The disclosure paragraph is the place to state it.
2. **"the TI-89 graphing calculator in 1999".** The 1999 paper says it was developed for
   the **TI-89 and TI-92 Plus** (section "Calculator selection"), and `calc/README.md`
   says versions 4–7 target the **TI-89 Titanium**, a later model. Suggested: *"first
   written in 1999 for the TI-89 and TI-92 Plus"*.
3. **"developed through successive calculator generations to the TI-Nspire CX II
   CAS"**: consistent with `calc/README.md` (v8 on the Nspire CX II CAS). Confirmed.
4. **"exact results for every node voltage, branch current, power and source impedance
   from a single call"** (State of the field, capability 2). Powers and source impedances
   exist only for `dc()`/`ac()` (`fd()`/`tr()` keys: `i_e1, i_r1, v_1` only). Add "in DC
   and AC". Also, Lcapy returns exact symbolic node voltages and currents too, so as
   written this is not a distinguishing capability. The distinction is that the whole
   set arrives **named, from one call, in the course's own names** (`v_2`, `i_r1`,
   `p_r1`). Say that.
5. **"inverse problems as a first-class operation"** as a distinguisher: a reviewer
   familiar with Lcapy will note that one can add an equation to its nodal system with
   SymPy. The honest distinction is that the added equation and unknown join the
   *same* system in the *same* call, with the circuit's own answer names usable inside
   it, including powers (`p_r2 = …`). Show one line of code; it is the paper's best
   argument.
6. **"Continuity … without rewriting them"** and **"material written for them runs
   unchanged"**: soften per 2g.
7. **Formulation paragraph:** replace per section 1. The sparse tableau citation can
   stay as a contrast or go.
8. **"the ninth version"**: consistent with the README ("Symbulator 9 is a port of
   Symbulator 8").
9. **Research impact: verifiable evidence exists in the project's own archive**
   (`Documentation/paper/references/README.md`). This was not re-verified here beyond
   what the catalogue records, so each item should be checked against its source
   before it is cited:
   - First place, **IEEE Region 9 Student Paper Competition**, certificate October
     2000 (the paper entered in 1999; *El NoticIEEEro* 28(4), Dec 2000, calls it the
     "1999 Regional Student Paper Contest"); scan at `2000_ieee_award_colour.jpg`.
   - Publication: *BURAN* nº 17, IEEE Student Branch Barcelona, Sept 2001, pp. 24–29,
     which reports users in seventeen countries half a year after release, with two
     named testimonials.
   - The 2000–01 graduation thesis (`references/2000_thesis/`).
   - The draft's "undergraduate thesis" and "IEEE award" TODOs should use these.
10. **Paper length:** 1,254 words of body text with the HTML comments removed, inside
    JOSS's 750–1,750 range, so there is room for the one-line inverse-problem example.
11. **Unresolved TODOs** remain (ORCID `0000-0000-0000-0000`, submission date, impact
    evidence, acknowledgements). Expected in a draft; listed for completeness.
12. **Bibliography:** `nilsson2019` must become the 12th edition (3b). `slicap`
    ("2026, version 5.2.1") and `ahkab` ("2015") were not verified online here. The DOIs
    for `ho1975`, `hachtel1971`, `meurer2017` and `hayes2022` match the standard
    records, but they were not re-fetched.

---

## Prioritised fixes

1. **Rewrite the Formulation paragraph** (section 1). As written, it says sparse tableau
   and every-branch-voltage unknowns, which is plainly contradicted by
   `engine.py`, and it claims derived quantities need no post-processing, which is
   false.
2. **Drop "companion equation-sheet tool" from the list of things the core runs, and
   fix "at symbulator.com"** (3a). Also drop "and of its documentation" from Research
   impact.
3. **Fix the Nilsson & Riedel edition** in `paper.bib`: 12th, not 11th (3b).
4. **Complete the AI disclosure** with Claude Fable 5.1, and say whose commits these
   are (4e.1).
5. **Soften "runs unchanged"** in Summary, Statement of need and Software design (2g),
   and qualify "floating point only where the user writes it" for polar phasors (2a).
6. **Repository readiness before submission** (4d): add a CI workflow (at least one
   Python version per supported minor, or narrow `requires-python`), tag a release
   matching the Zenodo archive, and add `CONTRIBUTING.md`, `CITATION.cff` and a code
   of conduct.
7. **Fix the README** (4a, 2d, 4b): the test count and files, the ahkab note, the two
   stale "reported floating" sentences, the quick-start `exp` output, and the
   notebooks README's missing `books/`.
8. **Sharpen State of the field** (4e.4–5) with the concrete one-call, named-answer and
   same-system inverse-problem example.
9. **Fill Research impact** from the archive's primary sources (4e.9), checking each.
10. ~~Keep **Development Status 4 - Beta** (4c).~~ Overruled: versions 9 and 8
    leave beta (#471); the classifier is `5 - Production/Stable`.
