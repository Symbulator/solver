# Changelog

## 0.5.0 -- 23 Aug 2026

### Added
- **`to_svg()` and `draw()`: a circuit description can now be drawn, not
  only solved.** `symbulator.schematic` renders the same string `dc()`,
  `ac()`, `fd()` and `tr()` already take into a standalone SVG, using only
  the standard library -- no matplotlib, no LaTeX, no external toolchain --
  so it runs unchanged in CPython and under Pyodide in the browser builds.
  Every stroke is `currentColor`, so one drawing serves a light and a dark
  page without being redrawn.

  The layout is deliberately not a general graph-drawing algorithm.
  Force-directed placement, which most netlist viewers reach for, produces
  a physics-plausible blob rather than something that reads as a schematic.
  This assumes instead the shape nearly every linear teaching circuit
  already has: ground as one rail along the bottom, anything touching it
  hanging vertically from it, anything between two live nodes running
  along a top row, and node order taken from a depth-first walk so a chain
  comes out as a chain. Anything that would collide -- a parallel element,
  or one reaching over an intermediate node -- is lifted onto its own row
  with risers, which is interval-graph colouring over the span each
  element occupies. Op-amps use the same colouring, with the colours
  becoming lanes down the middle band.

  Two details are taken from the engine rather than chosen, and must not
  be "corrected" without reading it: a voltage source's **+** goes on `n1`,
  because `_stamp_e` stamps `v(n1) - v(n2) = value`; and a coupled
  inductor's dot goes on `n1` of **every** coupled inductor, always,
  because the coupling enters as `+M*i_other` with no orientation term --
  reversed coupling is expressed as a *negative* M, so the dots never
  move and the sign appears in the caption instead. Mutual inductance is
  captioned rather than drawn, since `m` couples two elements rather than
  two nodes and a dashed tie between coils just reads as another wire.

  `to_svg` parses with `expand_si=False`, so a bare `1k` draws where the
  solver would stop and ask which it meant. A circuit can therefore be
  drawn before, or without, being solved -- which is when a picture helps
  most.

  Known limits, documented in the module: a bridge draws as a ladder with
  a jumper rather than the textbook diamond; an inductor coupled to two
  others with opposite signs cannot be drawn faithfully, the dot
  convention having no notation for it; a non-grounded op-amp `+` input is
  routed but may cross wires; and two-port blocks and the transformer draw
  as labelled boxes without their port parameters.

## 0.4.6 -- 22 Aug 2026

### Added
- **Every root of a circuit is now returned, not just the first.** An
  expert-mode equation written on a power is quadratic in its unknown, so a
  circuit like `e,1,0,e` / `r1,1,0,1'k` with `p_r1 = 0.025` is solved by
  `e = 5` *and* `e = -5`; both satisfy every constraint given. `solve_circuit`
  kept whichever SymPy happened to list first, which was the negative one, and
  presented it as the answer. `solve_circuit_all()` now returns them all, and
  `Result.solutions` exposes the list (`[values]` when there is only one, so
  the shape never varies), with `Result.multiple` as the flag and a `repr`
  banner naming the count. `solve_circuit()` is a thin wrapper returning the
  first, so `equiv`, `plotting` and `laplace` are unchanged. The ranking is
  `_rank_solutions`: it judges **design unknowns only** -- symbols not named
  `v_*` or `i_*`, since a node voltage or a branch current may perfectly well
  be negative -- putting all-real ahead of complex and all-non-negative ahead
  of negative, with ties keeping SymPy's order. So the root a person would
  have chosen leads, and the others remain available rather than discarded.
- **`symbulator.t` and `symbulator.s` are exported**, and `Result.at()`
  substitutes by *name*. The solver builds its time variable as
  `Symbol("t", positive=True)`; a user's own bare `Symbol("t")` is a different
  symbol, so `.subs()` silently did nothing and returned the expression
  unchanged. `res.at("v_2", t=0.001)` gives one value, `res.at(t=0.001)` a new
  Result with everything evaluated, `.solutions` included. Assumptions no
  longer have to be guessed at.

### Fixed
- **A floating sub-circuit solved silently.** `e1,1,0,5:r1,2,3,1` has nodes 2
  and 3 with no path to the reference node, and came back with `v_2 = v_3` and
  `r_e1 = oo` rather than an error. `_validate_topology` now runs a union-find
  over element terminals (an op-amp joins all three of its terminals, grounded
  two-port blocks tie both nodes to 0, `m` is skipped since it names inductors
  rather than nodes) and names the orphaned nodes.
- **Contradictory circuits gave a generic error.** Sources in parallel, a 0 Ohm
  resistor across a source, current sources in series -- all produced "Could
  not solve the system of equations… try symbolic values only", which is not
  what is wrong. `_diagnose_unsolvable` now names a voltage loop and lists its
  members, or names a node fed only by current sources. It runs only when
  `sp.solve` returns nothing, so the ordinary path is untouched.

### Security
- **Values and equations are checked before `sympify` sees them.** `sympify`
  is `eval` underneath, and a restricted namespace constrains only *names* --
  conditional expressions, lambdas, attribute access and subscripting all still
  ran. This matters for the web app, which feeds it strangers' input.
  `check_expression_syntax` parses with `ast` first and admits only numeric
  constants, plain names, arithmetic, unary sign, tuples, and calls of a bare
  function name with no keyword arguments; anything else raises
  `UnsafeExpressionError`. It is called inside `safe_sympify`, so values,
  `equations=` and `conditions=` are all covered.

### Documentation
- README no longer tells PyPI users to `pip install -r requirements.txt`, a
  file the distribution does not contain, and no longer links `llms.txt`
  relatively -- the link only resolved inside a checkout. Project URLs now
  include the source repository and the documentation site instead of pointing
  `Homepage` at PyPI itself. The package is described as Symbulator 9, matching
  symbulator.com.

## 0.4.5 — 21 Aug 2026

### Fixed
- **An expert-mode equation written on a derived quantity was silently
  discarded** -- `r_e`, `p_r1`, `v_r2`, `z_e` and the like. Those are
  computed by `analysis._derived()` *after* `solve_circuit()` returns, as
  algebra on the finished solution, so the solver had never heard of the
  names. The convenience that turns a brand-new symbol in an extra
  equation into an unknown then registered each one as a free variable
  that happened to share the name: `Eq(r_e, 12000)` was satisfied by
  setting that phantom to 12000, which cost the system nothing and told
  the circuit nothing. The answer came back correct but one constraint
  short -- parametrized in a leftover node voltage instead of resolved to
  numbers -- with nothing raised, nothing logged, and a result object
  that looked entirely normal. `engine._derived_definition()` now
  recognises a symbol naming a derived quantity of an element actually
  present in the circuit and stamps in the equation defining it in terms
  of the system's own unknowns, so the constraint lands on the circuit.
  The `r_`/`z_` forms are written multiplied out rather than as a
  division, keeping the system polynomial and stopping a zero current
  from putting a division by zero into it. Matching is against real
  element names rather than a prefix pattern, so ordinary labels like
  `pout`, `vin` and `r_b` are untouched unless they genuinely collide
  with an element in that circuit, and a name listed in `unknowns` is
  still registered first and left alone -- an explicit list continues to
  win.
- **An equation on a current held in `circuit.known` was discarded the
  same way** -- a `j` source's current, and a capacitor's in AC, are
  recorded rather than solved for, so `i_j1 = 0.005` became another
  phantom. Extra equations are now substituted against `known` before
  being stamped, turning that into a real constraint on the source's
  symbolic value. An equation left with nothing in it afterwards is
  dropped as redundant; one left as a flat contradiction now says so
  plainly instead of surfacing later as "could not solve the system".

### Changed
- **The AC power quantities refuse an expert-mode equation instead of
  ignoring one.** `s_`, `p_` and `ap_` in the AC domain are defined
  through `v * conjugate(i)`, and conjugation is not something
  `sympy.solve` can carry through a system, so there is no definition to
  stamp. They now raise `CircuitError` naming the quantity and pointing
  at the `v_`/`i_` restatement that does work. No working call breaks:
  none of these ever produced a constrained answer.

## 0.4.4 — 21 Aug 2026

### Added
- **`parse_circuit()` and `expand_shorthand()` take a new `expand_si`
  / `si` flag (default `True`, unchanged behaviour)** that, when set to
  `False`, leaves SI-prefix shorthand (`4.7'M`) in each value field
  exactly as typed instead of expanding it to a literal number. This is
  for callers that only want to echo a circuit description back to the
  user -- e.g. after normalising `i`/`I` to `j`, or after resolving a
  bare ambiguous suffix -- where the notation the person actually typed
  is worth more to them than the number it stands for. Solving still
  goes through the normal expansion (`expand_si=True`) as its own,
  separate parse, so this has no effect on any circuit's actual answers.

### Fixed
- **An AC element whose complex power should come back purely real or
  purely imaginary could instead show a tiny leftover in the other
  part** -- e.g. a resistor's power reading `0.006098 + 4.445e-18j`
  instead of plain `0.006098`, or an inductor's reading
  `-7.589e-19 + 0.006098j` instead of plain `0.006098j`. That leftover
  is ordinary floating-point noise from multiplying already-computed
  complex floats, and every rounding/display mode showed its own
  version of it -- including "exact", which showed the ugliest,
  full-precision version. `dc()`/`ac()` now recognise when one part of
  a complex power or impedance is negligible next to the other (with
  plenty of margin above the actual noise floor) and zero it out, so
  both parts are held to the same standard instead of each showing
  whatever noise it happened to accumulate. Exact/rational answers
  (e.g. from a circuit with no floats in it at all) are untouched, since
  they can't carry this kind of noise in the first place.

## 0.4.3 — 21 Aug 2026

### Fixed
- **"Third-level" quantities (a capacitor's current, a dependent
  current source's value, and anything derived from them like complex
  power) could come back still containing a raw node-voltage or
  branch-current symbol** -- e.g. `i_c1 = 0.001j*v_3` even though `v_3`
  itself was correctly solved to a plain number. These quantities are
  stamped in terms of the symbols `Circuit.v()` hands out *before* the
  KCL system is solved, and were never substituted with the final
  solved values afterwards -- on the original calculator they were
  evaluated on the fly instead. `solve_circuit()` now substitutes the
  solved system into every such quantity as its one evaluation pass, so
  they always come back fully resolved, same as every other answer.

## 0.4.2 — 20 Aug 2026

### Changed
- **`i`, `I`, `j` and `J` are reserved for the imaginary unit in AC
  only** (and in the AC mode of `th()`/`er()`/`port()`). Outside AC --
  `dc()`, `fd()`, `tr()`, and DC-mode `th()`/`er()`/`port()` -- there is
  no such thing as a complex component value, so those four letters are
  now free to use as ordinary variable or element-value names there,
  same as any other name. `safe_sympify()` and `hijacked_names()` take a
  new `reserve_imaginary` keyword (default `True`, matching 0.4.0's
  always-reserved behaviour) for callers that want the same
  domain-aware rule.

## 0.4.1 — 19 Aug 2026

### Fixed
- The `[a,b,c]` parallel-resistor shorthand is expanded correctly again.

### Added
- `time_samples()` and `bode_samples()`, powering the web front end's
  "Plot vs. time" and "Bode plot" tools.

## 0.4.0 — 18 Aug 2026

### Changed (breaking)
- **`i`, `I`, `j` and `J` are reserved for the imaginary unit** and can
  no longer be variable names. Every spelling now agrees: `3j`, `3*j`,
  `3*i`, `3*I` and bare `j` all mean the same thing. Previously `3*j`
  silently produced a variable, which looked right and gave a wrong
  answer.
- **Values are parsed against a restricted namespace.** Names SymPy
  would otherwise reinterpret — `Q`, `S`, `N`, `beta`, `gamma`, `E` and
  the like — are now ordinary variables, which is what someone writing
  `Q` for quality factor intends. `pi` and the maths functions (`exp`,
  `sqrt`, `sin`, `Heaviside`, …) still mean what they say. Euler's
  number is now written `exp(1)` rather than `E`.
- **Element letters, element names and node names are case-insensitive**
  and fold to lowercase: `R1` and `r1` are one resistor, `A` and `a` one
  node. Writing both spellings is now correctly reported as a duplicate
  instead of silently creating two elements. Values keep their case,
  because `'M` and `'m` differ by a billion.
- **The exa prefix is gone.** `E` belongs to scientific notation
  (`8E3` = 8000), which is worth more in a circuit than exa-ohms.
- **`ex()` no longer accepts a transient mode**, matching the
  calculator, whose prompt reads "Analysis? 1:DC 2:AC 3:FD". The
  previous docstring wrongly claimed the TI offered a fourth option.
  Call `tr()` directly for transient analysis.

### Added
- Both micro characters are accepted: MICRO SIGN (U+00B5) and GREEK
  SMALL LETTER MU (U+03BC) look identical and which one a keyboard
  produces is arbitrary, so `4.7'µ` works either way.
- `safe_sympify()` and `hijacked_names()` for callers that want the same
  parsing rules or want to tell a user which names were reinterpreted.

## 0.3.0 — 17 Aug 2026

### Changed (breaking)
- **Bare unit suffixes are no longer guessed.** A value like `1k` is
  ambiguous — it could mean the SI unit (`1'k` = 1000) or one times a
  variable named `k` (`1*k`) — so the default policy `suffix="ask"` now
  raises `AmbiguousValueError` listing every such value instead of
  silently choosing. Pass `suffix="si"` or `suffix="var"` to decide for
  a whole circuit, or write the explicit form. Code written against
  0.1.0 that used bare suffixes needs one of those changes.

### Added
- `find_ambiguous_values(desc)` scans a description for ambiguous
  values without solving, for callers that want to ask a user.
- Expert mode: `equations`, `unknowns` and `conditions` arguments on
  `dc`/`ac`/`fd`/`tr`/`ex` (and the tools), porting the original's
  "Add equations / Add unknowns / Add conditions" prompts. Conditions
  are solve-time substitutions, the calculator's `|` operator.
- Branch voltages are now stored as `v_<element>`, matching the
  `v<name>` variables the calculator kept.
- Circuit descriptions may separate elements with newlines as well as
  `:`.

### Fixed
- A source carrying no current (for example one feeding only a
  capacitor in DC) raised `ZeroDivisionError` out of mpmath when
  computing the resistance/impedance it sees. It now reports infinity,
  and the genuinely undefined 0 V / 0 A case omits the quantity.

### Docs
- The `s` element is described as a short circuit.

## 0.2.0 — never published
Superseded by 0.3.0 before release; its changes are listed above.

## 0.1.0 — 13 Aug 2026
First release: DC, AC, s-domain and transient analysis; Thevenin/Norton
equivalents; equivalent impedance; two-port parameter extraction; the
`ex()` dispatcher; unit shorthand; dependent sources.
