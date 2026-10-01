---
title: 'Symbulator: exact symbolic analysis of linear circuits in Python, from a calculator notation used since 1999'
tags:
  - Python
  - SymPy
  - circuit analysis
  - symbolic computation
  - electrical engineering
  - engineering education
authors:
  - name: Roberto Perez-Franco
    orcid: 0000-0002-2495-6993
    affiliation: 1
affiliations:
  - name: Independent Researcher, Melbourne, Australia
    index: 1
date: 1 October 2026   # TODO: update on submission day
bibliography: paper.bib
---

# Summary

Electrical circuits built from resistors, capacitors, inductors, sources and
amplifiers are described by systems of equations. Most circuit simulators solve
those equations with numbers: give them component values and they return
voltages and currents as decimals. `symbulator` solves them with algebra
instead. Component values may be numbers, letters, or expressions, and every
answer comes back as an exact formula — for example, the output of a voltage
divider as `rb*vin/(ra + rb)` rather than `6.0`. Formulas show *why* a circuit
behaves as it does, which is what engineers need when designing and what
students need when learning.

`symbulator` is a Python library built on SymPy [@meurer2017]. It performs DC,
AC (phasor), s-domain (Laplace) and transient analysis; computes Thévenin and
Norton equivalents and two-port parameters; and can solve *inverse* problems,
such as finding the resistor value that makes an output equal 6 V. It is the
ninth version of Symbulator, a program first written in 1999 for the TI-89 and
TI-92 Plus graphing calculators and developed through successive calculator
generations to the TI-Nspire CX II CAS. Circuits are written in the same
compact one-line notation the calculator versions have used, so descriptions
written for them run with few or no changes.

# Statement of need

Symbolic circuit analysis serves two groups. Designers use it to derive design
equations — transfer functions, gains, and component values as functions of
requirements — instead of iterating numerical simulations
[@gielen1991]. Educators and students use it because a symbolic answer can be
checked against a hand derivation step by step, which a number cannot
[@luchetta2001].

Symbulator was written for the second group and has served it for over two
decades on calculators, the tools students are permitted to carry into exams.
Moving it to Python addresses three needs the calculator versions could not:

1. **Reproducibility.** Analyses can live in scripts and Jupyter notebooks,
   version-controlled and re-run, rather than in calculator memory.
2. **Composability.** Every answer is an ordinary SymPy expression, so
   simplification, limits, plotting and numerical conversion
   (`lambdify`) work on it directly.
3. **Continuity.** Users with circuits, worked problems and course material
   written in Symbulator's notation over 25 years can bring them to an open,
   scriptable environment with little or no rewriting.

The target audience is instructors and students of first- and second-year
circuit analysis courses, and engineers who want closed-form results for small
and medium linear circuits.

# State of the field

Several open-source tools perform symbolic linear circuit analysis. Lcapy
[@hayes2022] is the most complete Python option: it accepts SPICE-like
netlists, represents values as domain-aware symbolic expressions, supports
noise and state-space analysis, and draws schematics. SLiCAP [@slicap] targets
structured analog design, with symbolic noise, pole-zero and root-locus
analysis and HTML report generation. SapWin [@luchetta2001; @grasso2016] is a
long-standing Windows application combining schematic capture with symbolic
analysis for teaching. Numerical Python simulators such as ahkab [@ahkab]
provide SPICE-like analyses, useful for cross-checking symbolic results.

*Build vs. contribute.* `symbulator` is not a new implementation in search of
users; it is the continuation of an existing program whose notation and
workflow already have them. Rebuilding it on Lcapy or SLiCAP would have meant
translating its grammar, its result naming (`v_2`, `i_r1`, `p_r1`), its
expert mode and its calculator conventions (unit suffixes such as `4'k`, RMS
versus peak power) into another package's object model, breaking existing
material for features its audience does not use.

Two things distinguish it in use. First, a single call returns the whole set of
quantities an introductory course asks for, exactly and under the course's own
names: every node voltage and element current in all four analyses, and in DC
and AC every element's voltage drop and power and the impedance each source
sees. Second, inverse problems use the same system as analysis: an extra
equation and an extra unknown join the circuit's own equations and are solved
with them in one call, and the circuit's answer names can be used inside the
added equation.

```python
from symbulator import dc
res = dc("e1,1,0,12:r1,1,2,1'k:r2,2,0,r_b",
         equations=["v_2 = 6"], unknowns=["r_b"])
res["r_b"]    # 1000, with every other answer at that value
```

<!-- TODO(Roberto): check and sharpen this section. Reviewers will read it
closely. If there is anything Lcapy or SLiCAP cannot do that Symbulator can,
state it concretely here. -->

# Software design

**One notation, many front ends.** The package is the solver core. A circuit is
a single string of colon-separated elements (`e1,1,0,5:r1,1,2,1'k:r2,2,0,1'k`),
parsed into a system of equations that is handed to SymPy. The same core runs
the Symbulator web application, both the hosted version and an offline build
that runs in the browser through Pyodide, where it also writes the equation
systems the application hands to its numerical equation-sheet tool. It also
provides Jupyter cell magics (`%%dc`, `%%ac`, `%%fd`, `%%tr`) and is usable
from any script. Keeping one grammar across all of them was a deliberate choice
over adopting SPICE syntax: it preserves compatibility with 25 years of user
material, at the cost of unfamiliarity to SPICE users. Translators to and from
the linear subset of SPICE are provided for exchange with other tools.

**Formulation.** The solver generates the circuit's equations directly and
hands them, as a list, to SymPy's `solve`; no matrix is assembled. It writes
Kirchhoff's current law at every non-reference node and one defining equation
for each element that carries its own current: resistors, inductors, voltage
sources, shorts, op-amp outputs, transformer windings and two-port terminals.
The unknowns are the node voltages and those element currents. Capacitor and
current-source currents are written directly in terms of node voltages and
substituted into Kirchhoff's current law. In the terms of modified nodal
analysis [@ho1975], most elements are in the group whose currents are
retained, which gives a system somewhat larger than minimal modified nodal
analysis but, unlike the sparse tableau approach [@hachtel1971], with no
branch-voltage unknowns. Named element currents let a dependent source or an added
equation refer to `i_r1` directly. Voltage drops, powers and source impedances are computed from the
solution afterwards, in DC and AC. This *equation generation* design dates from
the 1999 calculator version, where it was chosen over nodal matrix methods for
its handling of dependent sources, transformers and two-ports. It suits the small and medium circuits of teaching and design
derivations; it is not intended for large netlists.

**Exactness by default.** Inputs are parsed as exact rationals where possible,
so a 5 V source across two 1 kΩ resistors gives `5/2`, not `2.5`. A decimal the
user types stays a floating-point number. A phasor written in polar form, such
as `(120∠30°)`, is deliberately converted to a rectangular floating-point
number: an angle that SymPy cannot reduce to closed form would otherwise be
carried unevaluated through every equation, and a three-phase textbook circuit
that solves in about a second with rectangular sources had not finished after
25 seconds in exact polar form.

**Explicit domains.** `tr()` reads source values as functions of time and
Laplace-transforms them; `fd()` reads them as expressions in *s* and leaves
them alone. A constant `5` is therefore a step to `tr()` and an impulse to
`fd()`; a time-domain value can be given to `fd()` in braces, `{5}`. Making the
distinction explicit, rather than guessing, avoids a class of silent errors.

**Refusing to guess.** Where input is ambiguous, the package asks rather than
assumes. A bare suffix such as `1k` may mean 1000 or `1*k`, so by default it
raises an error listing every ambiguous value; the calculator's quoted form
`1'k` is always unambiguous. A section of a circuit connected to the rest only
through a transformer, a two-port block or a mutual inductance is given an
explicit local reference, and the result says which node was chosen; a section
with no connection at all is refused as floating.

**Inverse problems through the same system.** Extra equations and unknowns
(`equations=`, `unknowns=`) join the circuit's own equation set before solving,
and `conditions=` substitute values into it, as the calculator's `|` operator
did, so design questions and analysis questions use one mechanism.

**Testing.** The suite checks answers against textbook circuits and the SPICE
exporter against ahkab, on Python 3.9 to 3.14 in continuous integration.

# Research impact statement

<!-- TODO(Roberto): the comments below are undated and all concern the
TI-89 versions (Symbulator 3, Q and 4, and the 2000 award). Add dates if
you have them, any adoption by an instructor (a course that recommended or
required it), and any later evidence (versions 6-9). PyPI downloads and
GitHub stars were checked on 1 Oct 2026 and left out: 60 releases in seven
weeks inflate the downloads, and the repository has no stars yet. -->

Symbulator has been developed and distributed since its first calculator
release in 1999. The paper describing the original TI-89 program won first
place in the 2000 IEEE Region 9 Student Paper Competition, and the program was
the subject of the author's graduation thesis at the Universidad Tecnológica de
Panamá [@perezfranco2001thesis]. Half a year after its release on the
internet, the author reported users among students and engineers in fourteen
named countries, including a single Texas class in which twelve students used
it [@perezfranco2001buran]. The comments users sent about the calculator
versions, published by the author [@perezfranco_comments_en;
@perezfranco_comments_es], number 83 from 74 people at more than thirty
universities in twenty countries. They describe it as a way to check homework
and exam answers and to understand circuits; one student recommends it for named circuits courses at the University of
Kentucky, another reports about thirteen users in a single group at the
University of Central Florida, and several describe passing it to their
classmates. A practising engineer reports using it to check answers while
preparing for the Professional Engineering exam.

The Python package is the computational core of the Symbulator web
application. The repository includes executed notebooks, each opening in
Google Colab, that run every worked problem of the Symbulator tutorial and two
samplers of problems from standard circuit-analysis textbooks
[@alexander2021; @nilsson2023]. A separate script checks each notebook's
answers against the web application's, entry by entry; on the two textbook
samplers and the tutorial's first lesson it compares 126 entries and 2,449
answers with no difference.

# AI usage disclosure

Generative AI was used in developing this software and in preparing this
paper. The Python port was developed with Claude Code, using Anthropic's
Claude Sonnet 5, Claude Opus 5, Claude Fable 5 and Claude Fable 5.1 models,
for code generation, refactoring, test scaffolding and documentation drafting;
the models are named as co-authors in the trailers of the repository's
commits, which are made under the project's own account. The first draft of
this paper was written with Claude Opus 5.5 from the repository's
documentation and the author's answers to questions, and was then checked
claim by claim against the code by running it, again with Claude Opus 5.5.

The author defined the problem, made all core design decisions (the notation,
the formulation, the handling of domains and ambiguous input, and
compatibility with the calculator versions), and reviewed, edited and
validated all AI-assisted output. Correctness was verified by running the test
suite, by comparing results against the calculator and web-application
versions of Symbulator, and against textbook answers in the executed
notebooks.

<!-- TODO(Roberto): confirm this matches how you worked, and list any other
tools (e.g., other assistants for copy-editing). -->

# Acknowledgements

<!-- TODO(Roberto): anyone who helped. -->

This work received no specific funding.

# References
