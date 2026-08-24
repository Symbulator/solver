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

import ast
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


# The `{...}` shorthand, from symbv8si:
#
#     If betatool="fd" and inString(sitext,"{") Then
#       symbv8sr("{", "s\t2s(")
#       symbv8sr("}", ")")
#
# FD reads its source values in the s-domain. Wrapping one in braces says
# "this one is written in time -- convert it", which is exactly `t2s(...)`
# and five characters shorter. It is deliberately FD-only: TR converts its
# sources anyway, so there would be nothing for it to do there.
#
# A plain textual swap, as the original's is. The braces cannot nest and
# cannot contain a comma that matters -- a value containing one would
# already have been split into separate fields long before here.


def expand_time_domain_braces(text: str) -> str:
    """`{expr}` -> `t2s(expr)`, for a source value written in time."""
    if "{" not in text:
        return text
    return text.replace("{", "t2s(").replace("}", ")")


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


# The calculator's names for the step and the impulse, so a description
# written for versions 7 and 8 reads unchanged in version 9.
#
# `u` is the hard one, because it is also the micro prefix, and Roberto
# fixed the rule on 24 Aug 2026: whether a `(` follows decides it.
#
#     7'u      micro      the quoted prefix, untouched here
#     7u       micro      a bare suffix, left for _BARE_SUFFIX_RE
#     7*u(t)   function   an explicit multiplication
#     7u(t)    function   the same, with the multiplication implied
#
# So only `u(` is rewritten, never a bare `u` -- which also means someone
# using `u` as a plain variable keeps it, unlike the names in
# _allowed_namespace, which are taken away everywhere.
#
# The implied multiplication in `7u(t)` has to be made explicit here too:
# nothing later in the chain infers one, and `7Heaviside(t)` is a syntax
# error rather than a product.
_STEP_RE = re.compile(r"(?<![A-Za-z0-9_.])(\d+\.?\d*)?\s*"
                      r"(u|δ|delta)\s*\(")
_STEP_FN = {"u": "Heaviside", "δ": "DiracDelta", "delta": "DiracDelta"}


def _expand_step_and_impulse(text: str) -> str:
    """`u(t)` -> `Heaviside(t)`, the delta -> `DiracDelta(t)`, inserting the
    multiplication a leading number implies."""
    def swap(m):
        number, name = m.group(1), m.group(2)
        head = f"{number}*" if number else ""
        return f"{head}{_STEP_FN[name]}("
    return _STEP_RE.sub(swap, text)


# The calculator's power notation and its implied multiplications.
#
# Both are habits every Symbulator 7/8 user has, and both used to fail in
# version 9 -- `2^3` was rejected outright (a caret is XOR in Python, which
# the AST guard refuses) and `2ir3` came back "invalid decimal literal".
# Between them they broke 37 of the 50 circuits in the version 9
# documentation.
#
# Scientific notation is the trap here. `1e-6`, `2.5e3` and `1E6` are
# ordinary numbers that SymPy already reads, and a naive "digit followed by
# a letter means multiply" rule turns `2.5e3` into `2.5*e3`, silently
# replacing a number with a symbol. So the exponent form is matched first
# and stepped over.
_SCI_RE = re.compile(r"\d\.?\d*[eE][+-]?\d+")

# The other thing that must survive untouched is a bare engineering suffix:
# `1k` is a thousand, not one times k, and `4.7u` is micro. Those are read
# further along (expand_value, find_ambiguous_values), which never gets the
# chance if a `*` has already been pushed into the middle of them. Letters
# outside this set -- the `t` in `2t`, the `i` in `2ir3` -- are not suffixes
# and do get the multiplication.
_BARE_UNIT_RE = re.compile(r"\d\.?\d*[kKMGTPmuµμnpfa](?![\w])")

# A number meeting a name or an opening bracket, or a bracket meeting
# either -- never a name meeting a bracket, which is a function call.
# The number must not be part of a name. Without the lookbehind, `t2s(t)`
# becomes `t2*s(t)` and the function disappears -- which broke t2s and s2t
# themselves, the two names most likely to be typed here.
_IMPLICIT_NUM = re.compile(r"(?<![A-Za-z_])(\.?\d+\.?\d*)(?=[A-Za-z_(])")
_IMPLICIT_PAREN = re.compile(r"(?<=\))(?=[\w(])")


def _insert_implicit_multiplication(text: str) -> str:
    """`2ir3` -> `2*ir3`, `2(a+b)` -> `2*(a+b)`, `(a)(b)` -> `(a)*(b)`."""
    # Protect scientific notation, then put it back untouched.
    kept = []

    def stash(m):
        kept.append(m.group(0))
        return f"\x00{len(kept) - 1}\x00"

    guarded = _SCI_RE.sub(stash, text)
    guarded = _BARE_UNIT_RE.sub(stash, guarded)
    guarded = _IMPLICIT_NUM.sub(r"\1*", guarded)
    guarded = _IMPLICIT_PAREN.sub("*", guarded)
    for n, original in enumerate(kept):
        guarded = guarded.replace(f"\x00{n}\x00", original)
    return guarded


def _expand_caret(text: str) -> str:
    """`2^3` -> `2**3`, and `e^x` -> `exp(x)`.

    `e` has to become Euler's number rather than a symbol, but only where a
    caret follows: putting `e` in the namespace would take it away from
    everyone using it as an ordinary variable, the way `re` and `exp`
    already are. So the exponent's extent is found here instead -- a
    bracketed group, or a sign and one number or name -- and wrapped in a
    real exp() call.
    """
    out, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch != "^":
            out.append(ch)
            i += 1
            continue

        # Is this the calculator's e^, rather than some other base?
        # A digit before the `e` is a coefficient -- `2e^3` is two times
        # Euler's number cubed. Only a letter or underscore means the `e`
        # is the tail of a name, as in `re^2`, where it is not Euler's.
        base_is_e = (out and out[-1] == "e"
                     and (len(out) < 2 or not (out[-2].isalpha()
                                               or out[-2] == "_")))
        j = i + 1
        if j < len(text) and text[j] == "(":
            depth, k = 1, j + 1
            while k < len(text) and depth:
                depth += (text[k] == "(") - (text[k] == ")")
                k += 1
            exponent, j = text[j + 1:k - 1], k
        else:
            k = j
            if k < len(text) and text[k] in "+-":
                k += 1
            while k < len(text) and (text[k].isalnum() or text[k] in "_."):
                k += 1
            exponent, j = text[j:k], k

        if base_is_e:
            out.pop()
            out.append(f"exp({exponent})")
        else:
            out.append(f"**({exponent})")
        i = j
    return "".join(out)


def expand_shorthand(text: str, si: bool = True) -> str:
    """Expand `'k`/`'M`/... unit-prefix shorthand and `[...]` parallel-
    impedance shortcuts in `text`, mirroring symbv8si.

    `[a,b,c]` becomes `pr(a,b,c)` (a call into utils.pr), matching how
    the original turned `[...]` into `s\\pr({...})`.

    `si=False` skips the `'`-prefix substitution (and its "unrecognized
    shorthand" check) while still doing the `[...]` rewrite, which is
    needed unconditionally so `_split_fields` can tell the difference
    between the shortcut's inner commas and an element's own field
    commas. This lets a caller that only wants the circuit *echoed back*
    (not solved) keep the SI-prefix notation the user actually typed --
    it is only expanded to a literal number just before solving."""
    result = text

    if "[" in result:
        result = result.replace("[", "pr(").replace("]", ")")

    # Only when the value is on its way to being solved. `si=False` means
    # the caller wants the circuit echoed back the way it was typed -- the
    # web app puts that straight back into the Circuit Description box --
    # and rewriting `u(t)` to `Heaviside(t)` there would take the
    # calculator's notation away from someone who deliberately used it,
    # silently, on the first Run. The `[...]` rewrite above is different:
    # it has to happen unconditionally, because _split_fields cannot tell
    # the shortcut's inner commas from an element's own without it.
    if si:
        result = _expand_step_and_impulse(result)
        if "^" in result:
            result = _expand_caret(result)
        result = _insert_implicit_multiplication(result)

    if si and "'" in result:
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
def _allowed_namespace(reserve_imaginary: bool = True):
    """Build the small dict of names `safe_sympify`/`hijacked_names` treat
    as meaning something other than a plain variable: a handful of
    constants (pi, oo) and functions (trig, exp/log, Heaviside/DiracDelta
    for transient sources, Min/Max) that a circuit description could
    genuinely need, plus -- when `reserve_imaginary` is true -- the four
    imaginary-unit spellings. Built fresh on each call rather than as a
    module-level constant purely so the `import sympy as sp` stays local
    to the handful of functions that need it, matching this module's
    style of keeping SymPy import cost out of code paths that don't
    touch it.

    `reserve_imaginary` is false outside AC analysis (and outside the AC
    mode of the equivalence tools): i, I, j and J only ever mean
    something to a circuit when a source or component value can be
    complex, which only happens in AC, so there's no reason to take
    those four names away from someone writing a DC or s-domain
    circuit."""
    import sympy as sp
    # Imported here rather than at module level: laplace imports
    # analysis, which imports this module, so a top-level import
    # would be a cycle. The same reason `pr` has always been local.
    from .laplace import S, T, s2t, t2s
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
        # The version 7 aids for moving an expression between the
        # time and complex frequency domains, which had no way in
        # before. `pf` is deliberately NOT here: it returns a
        # sentence ("pf: 0.6 lagging"), not an expression, so
        # sympify hands back a Python str and every formatter
        # downstream is expecting a SymPy object.
        "t2s": t2s, "s2t": s2t,
        # `s` is the solver's own symbol. `t` is deliberately NOT:
        # tr() writes its answers in Symbol("t", positive=True), but
        # binding that here changes what expressions *mean* rather than
        # only which symbol they use -- SymPy evaluates DiracDelta of a
        # strictly positive argument to 0, so `delta(t)` silently became
        # nothing and an impulse source disappeared from the circuit.
        # Parse with a neutral t; the transforms below reconcile the two.
        "t": sp.Symbol("t"), "s": S,
    }
    if reserve_imaginary:
        # i, I, j and J all mean the imaginary unit. Reserving all four
        # is what lets `3*j` be unambiguous: no variable may use those
        # names, so there is nothing else they could mean.
        for name in _IMAGINARY_NAMES:
            ns[name] = sp.I
    return ns


_IDENT_RE = re.compile(r"(?<![\w.])([A-Za-z_]\w*)")


def hijacked_names(text: str, reserve_imaginary: bool = True):
    """Names in `text` that SymPy would quietly reinterpret as something
    other than a variable -- `Q`, `N`, `beta`, `E` and friends. Returned
    so the caller can tell the user they were read as plain variables.

    `reserve_imaginary` must match whatever was passed to `safe_sympify`
    for the same text, so this never reports i/I/j/J as "hijacked" when
    they were in fact read as ordinary variables (outside AC)."""
    import sympy as sp

    allowed = _allowed_namespace(reserve_imaginary)
    found = []
    for name in dict.fromkeys(_IDENT_RE.findall(text)):
        if name in allowed:
            continue
        if not reserve_imaginary and name in _IMAGINARY_NAMES:
            # Deliberately plain symbols here, not a SymPy built-in that
            # got in the way -- so this isn't a "hijack" to report.
            continue
        looked_up = getattr(sp, name, None)
        if looked_up is not None and not isinstance(looked_up, sp.Symbol):
            found.append(name)
    return found


class UnsafeExpressionError(ValueError):
    """A value or equation contains Python syntax that is not arithmetic."""


_SAFE_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod)
_SAFE_UNARY = (ast.UAdd, ast.USub)

# The syntax tree's own class names -- IfExp, Subscript, ListComp -- are
# Python's vocabulary, not a circuit-solver user's, and the message a person
# reads should describe what they wrote. Anything not listed falls back to a
# phrase that names nothing rather than naming the wrong thing.
_PLAIN_NAMES = {
    "IfExp": "a conditional expression",
    "Compare": "a comparison",
    "BoolOp": "a boolean operator",
    "Lambda": "a lambda",
    "Attribute": "attribute access with a dot",
    "Subscript": "square-bracket indexing",
    "List": "a list",
    "Dict": "a dictionary",
    "Set": "a set",
    "ListComp": "a comprehension",
    "SetComp": "a comprehension",
    "DictComp": "a comprehension",
    "GeneratorExp": "a comprehension",
    "Starred": "a starred argument",
    "Slice": "a slice",
    "JoinedStr": "a formatted string",
    "NamedExpr": "an assignment",
    "Await": "an await",
    "Yield": "a yield",
}


def check_expression_syntax(text: str) -> None:
    """Refuse `text` unless it is plain arithmetic: numbers, names, the
    operators + - * / ** %, parentheses, and calls of named functions.

    sympify() hands the string to Python's eval, and the restricted
    namespace in `_allowed_namespace` only governs *names* -- Python
    syntax such as conditionals, comprehensions, lambdas, attribute
    access, subscripts and strings would still execute. Checking the
    syntax tree first makes the namespace trick unnecessary as a
    security boundary; it is what lets the web app accept circuit
    strings from strangers. Raises UnsafeExpressionError."""
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpressionError(
            f"Could not read the value '{text.strip()}': {exc.msg}.") from None

    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.Load)):
            continue
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float, complex)) \
                    and not isinstance(node.value, bool):
                continue
            bad = repr(node.value)
        elif isinstance(node, ast.Name):
            if node.id.startswith("__"):
                bad = node.id
            else:
                continue
        elif isinstance(node, ast.BinOp) and isinstance(node.op, _SAFE_BINOPS):
            continue
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, _SAFE_UNARY):
            continue
        elif isinstance(node, (ast.Tuple, *_SAFE_BINOPS, *_SAFE_UNARY)):
            continue
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and not node.keywords:
                continue
            bad = "a call that is not a plain function name"
        else:
            bad = _PLAIN_NAMES.get(type(node).__name__, "something")
        raise UnsafeExpressionError(
            f"The value '{text.strip()}' contains {bad}, which is not arithmetic. "
            "Values may use numbers, symbols, + - * / ** and function calls "
            "such as sqrt(2) or exp(-3)."
        )


def safe_sympify(text: str, reserve_imaginary: bool = True):
    """sympify() restricted to the namespace above: every identifier that
    isn't an intended constant or function becomes a plain Symbol.

    `reserve_imaginary` (default true, for backward compatibility with
    every caller that isn't domain-aware) controls whether i/I/j/J parse
    as the imaginary unit or as ordinary symbols -- pass false for any
    analysis where complex values don't apply (dc, fd, tr)."""
    import sympy as sp

    check_expression_syntax(text)
    ns = _allowed_namespace(reserve_imaginary)
    for name in set(_IDENT_RE.findall(text)):
        ns.setdefault(name, sp.Symbol(name))
    return sp.sympify(text, locals=ns)
