# Changelog

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
