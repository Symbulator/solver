# Changelog

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
