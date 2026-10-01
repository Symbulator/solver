# Contributing to symbulator

Thank you for taking the time. Symbulator is maintained by Roberto
Perez-Franco, and every report is read.

## Reporting a wrong answer, a crash or a confusing message

Open an issue at <https://github.com/Symbulator/solver/issues>. The most
useful report has four things:

1. **The circuit description**, exactly as typed, for example
   `e1,1,0,5:r1,1,2,1'k:r2,2,0,1'k`.
2. **The call**, for example `dc(desc)` or `ac(desc, omega=1000)`, with
   any `equations=`, `unknowns=` or `conditions=`.
3. **What you got and what you expected**, and where the expected answer
   comes from (a textbook and page, a hand derivation, another simulator).
4. **The version**: `python -c "import symbulator; print(symbulator.__version__)"`.

A circuit that can be cut down to the smallest one that still shows the
problem is worth the effort: it is usually the fastest route to a fix.

Questions about how to describe a circuit are welcome as issues too. The
documentation at <https://learn.symbulator.com> and the README's *Circuit
description syntax* section answer most of them.

## Proposing a change

Pull requests are welcome. Before opening one:

- **Run the suite**: `pip install -e ".[test]"` and `pytest symbulator/tests`.
  It must pass. GitHub Actions runs it on Python 3.9 to 3.14 for every
  pull request.
- **Add a test that fails without your change.** A test for a solver fix
  should check an answer, not only that no exception was raised, and on a
  branch that carries real current (a test that multiplies its subject by
  zero proves nothing).
- **Keep answers exact.** Inputs are read as exact rationals wherever the
  user wrote exact values; do not introduce floating point on the way.
  The one deliberate exception is a phasor in polar form, which is
  converted to a rectangular number (see the comment in `si_prefix.py`).
- **Keep the notation.** The circuit-description grammar is shared with the
  calculator versions and the web application, and changes to it reach
  every user's existing files. Discuss a grammar change in an issue first.
- **Messages are codes.** Errors and notes the package raises carry a code
  from `symbulator/messages.py` so the web application can translate them.
  Add a code rather than a bare string.
- **Note it in `CHANGELOG.md`** under a new heading for the next version.

By contributing you agree that your contribution is licensed under the
project's MIT licence.

## Conduct

Everyone taking part is expected to follow the
[code of conduct](CODE_OF_CONDUCT.md).
