"""
Port of Symbulator's `symbv8si` / `symbv8sr` shorthand expansion.

On the calculator, values could be written with a unit-prefix shorthand
like `1'k` (1 kilo = 1e3) instead of typing `*10^3` by hand. The original
TI-Basic did a series of literal substring replacements (see `symbv8sr`,
called repeatedly from `symbv8si`). We reproduce the same substitution
table here, operating on plain Python strings, so circuit descriptions
written in the calculator's shorthand can be reused unchanged.

Note: the original also special-cased `{...}` (Laplace-of-time-function,
fd mode only) and `[...]` (parallel-impedance shortcut -> pr({...})).
The `[...]` shortcut is implemented; the fd-only `{...}` shortcut is not
(fd/tr analysis is out of scope for this phase).
"""

from __future__ import annotations

import re

# (old substring, new substring) pairs, applied in this order -- mirrors
# the exact sequence of symbv8sr calls inside symbv8si.
# Exa is deliberately absent: "E" is reserved for scientific notation
# (8E3 = 8000), which is far more useful in a circuit than exa-ohms.
_SI_PREFIXES = [
    ("'k", "*10**3"),
    ("'K", "*10**3"),
    ("'M", "*10**6"),
    ("'G", "*10**9"),
    ("'T", "*10**12"),
    ("'P", "*10**15"),
    ("'m", "*10**-3"),
    ("'u", "*10**-6"),
    ("'\u00b5", "*10**-6"),   # MICRO SIGN
    ("'\u03bc", "*10**-6"),   # GREEK SMALL LETTER MU -- looks identical,
                               # and which one you get depends on the
                               # keyboard, so accept both.
    ("'n", "*10**-9"),
    ("'p", "*10**-12"),
    ("'f", "*10**-15"),
    ("'a", "*10**-18"),
]


class ShorthandError(ValueError):
    """Raised when circuit-description shorthand can't be expanded."""


class AmbiguousValueError(ValueError):
    """Raised when a value like "1k" could mean either an SI unit
    (1'k = 1000) or a number times a variable (1*k), and the caller
    hasn't said which. `tokens` is a list of dicts, one per ambiguous
    value: {"element", "token", "number", "letter"}."""

    def __init__(self, tokens):
        """`tokens` is the list of ambiguous-value dicts found (see the
        class docstring); building the human-readable message here means
        callers that only want to display the error can just str() the
        exception, while callers that want to prompt the user field-by-
        field (like the web front end) can still read `.tokens` directly."""
        self.tokens = tokens
        listing = ", ".join(
            f"'{t['token']}' in {t['element']}" for t in tokens)
        super().__init__(
            f"Ambiguous value(s): {listing}. Write the SI-unit meaning "
            f"explicitly with an apostrophe (e.g. 1'k = 1000) or the "
            f"variable meaning with a star (e.g. 1*k), or pass "
            f"suffix='si' / suffix='var' to choose for all of them."
        )


# Convenience beyond the original calculator syntax: allow the common
# engineering-notation bare suffix ("1k", "4.7u", "10n") on a standalone
# numeric value field, in addition to the calculator's own `'k` syntax.
# Applied only when the *entire* field is just <number><suffix>, so it
# can't accidentally rewrite part of a symbolic expression.
_BARE_SUFFIX_EXP = {
    "k": 3, "K": 3, "M": 6, "G": 9, "T": 12, "P": 15,
    "m": -3, "u": -6, "\u00b5": -6, "\u03bc": -6,
    "n": -9, "p": -12, "f": -15, "a": -18,
}
_BARE_SUFFIX_RE = re.compile(r"^([+-]?\d+\.?\d*)([kKMGTPmu\u00b5\u03bcnpfa])$")


def bare_suffix_match(text: str):
    """Return the (number, letter) parts if `text` is a bare
    engineering-notation value like "1k" / "4.7u", else None."""
    m = _BARE_SUFFIX_RE.fullmatch(text.strip())
    return m.groups() if m else None


def expand_value(text: str, suffix: str = "si") -> str:
    """Expand a single value field. A bare engineering-notation suffix
    ("1k", "4.7u", ...) is inherently ambiguous -- 1k could mean the SI
    unit (1'k = 1000) or one times a variable named k (1*k) -- so the
    `suffix` policy decides: "si" reads it as the SI unit, "var" as
    number*variable, and "ask" refuses with AmbiguousValueError so the
    caller can ask the user. Fields that aren't bare-suffix values pass
    through the calculator's `'k`-style shorthand expansion unchanged."""
    stripped = text.strip()
    m = _BARE_SUFFIX_RE.fullmatch(stripped)
    if m:
        num, suf = m.groups()
        if suffix == "var":
            return f"({num})*{suf}"
        if suffix == "ask":
            raise AmbiguousValueError([{"element": "?", "token": stripped,
                                        "number": num, "letter": suf}])
        return f"({num})*10**{_BARE_SUFFIX_EXP[suf]}"
    return expand_shorthand(text)


def expand_shorthand(text: str) -> str:
    """Expand `'k`/`'M`/... unit-prefix shorthand and `[...]` parallel-
    impedance shortcuts in `text`, mirroring symbv8si.

    `[a,b,c]` becomes `pr(a,b,c)` (a call into utils.pr), matching how
    the original turned `[...]` into `s\\pr({...})`.
    """
    result = text

    if "[" in result:
        result = result.replace("[", "pr(").replace("]", ")")

    if "'" in result:
        for old, new in _SI_PREFIXES:
            result = result.replace(old, new)
        if "'" in result:
            raise ShorthandError(
                "Circuit description uses shorthand that Symbulator does not recognize."
            )

    return result


# ---------------------------------------------------------------------------
# Safe parsing of user-written values
# ---------------------------------------------------------------------------
#
# sympify() evaluates its input against SymPy's whole namespace, which
# means a value written `Q` becomes an internal assumptions object, `N`
# becomes a function, and `beta` becomes a function class -- none of
# which a person typing a circuit could possibly intend. Worse, they
# fail quietly rather than loudly.
#
# So values are parsed against a deliberately small namespace: the
# imaginary unit, pi, and the handful of mathematical functions a
# circuit genuinely needs. Every other name becomes an ordinary symbol,
# which is what someone writing `Q` for quality factor meant all along.

_IMAGINARY_NAMES = ("i", "I", "j", "J")

#: Names a value is allowed to mean something special by.
def _allowed_namespace():
    """Build the small dict of names `safe_sympify`/`hijacked_names` treat
    as meaning something other than a plain variable: a handful of
    constants (pi, oo) and functions (trig, exp/log, Heaviside/DiracDelta
    for transient sources, Min/Max) that a circuit description could
    genuinely need, plus the four imaginary-unit spellings. Built fresh
    on each call rather than as a module-level constant purely so the
    `import sympy as sp` stays local to the handful of functions that
    need it, matching this module's style of keeping SymPy import cost
    out of code paths that don't touch it."""
    import sympy as sp
    from .utils import pr

    ns = {
        "pi": sp.pi,
        "oo": sp.oo,
        "exp": sp.exp, "log": sp.log, "ln": sp.log, "sqrt": sp.sqrt,
        "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
        "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
        "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
        "Abs": sp.Abs, "abs": sp.Abs, "re": sp.re, "im": sp.im,
        "arg": sp.arg, "conjugate": sp.conjugate, "sign": sp.sign,
        "Heaviside": sp.Heaviside, "DiracDelta": sp.DiracDelta,
        "Min": sp.Min, "Max": sp.Max,
        # The `[...]` parallel-impedance shortcut expands to a literal
        # `pr(...)` call (see expand_shorthand below), so `pr` has to
        # resolve to the real function here or that call fails with
        # "'Symbol' object is not callable" once it reaches sympify.
        "pr": pr,
    }
    # i, I, j and J all mean the imaginary unit. Reserving all four is
    # what lets `3*j` be unambiguous: no variable may use those names,
    # so there is nothing else they could mean.
    for name in _IMAGINARY_NAMES:
        ns[name] = sp.I
    return ns


_IDENT_RE = re.compile(r"(?<![\w.])([A-Za-z_]\w*)")


def hijacked_names(text: str):
    """Names in `text` that SymPy would quietly reinterpret as something
    other than a variable -- `Q`, `N`, `beta`, `E` and friends. Returned
    so the caller can tell the user they were read as plain variables."""
    import sympy as sp

    allowed = _allowed_namespace()
    found = []
    for name in dict.fromkeys(_IDENT_RE.findall(text)):
        if name in allowed:
            continue
        looked_up = getattr(sp, name, None)
        if looked_up is not None and not isinstance(looked_up, sp.Symbol):
            found.append(name)
    return found


def safe_sympify(text: str):
    """sympify() restricted to the namespace above: every identifier that
    isn't an intended constant or function becomes a plain Symbol."""
    import sympy as sp

    ns = _allowed_namespace()
    for name in set(_IDENT_RE.findall(text)):
        ns.setdefault(name, sp.Symbol(name))
    return sp.sympify(text, locals=ns)
