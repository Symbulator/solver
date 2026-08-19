"""
`ex()`: the "expert mode" entry point -- ports `ex()`.

On the calculator this interactively asked "1:DC 2:AC 3:FD 4:TR" and
then called the matching tool. As a library there's no prompt to
answer, so `ex()` just takes the domain as a normal argument (either
the word or the calculator's own 1-4 shorthand) and dispatches to
`dc()`/`ac()`/`fd()`/`tr()` -- a single entry point for callers that
want to pick the analysis type dynamically (e.g. from user input in
their own application) rather than calling a specific function.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .analysis import Result, dc, ac, fd
from .laplace import tr  # noqa: F401  (re-exported for convenience)

# The calculator's ex() offers exactly three: its prompt reads
# "Analysis? 1:DC 2:AC 3:FD". Transient is not among them -- use tr()
# directly for that.
_DOMAIN_ALIASES = {
    "1": "dc", "dc": "dc",
    "2": "ac", "ac": "ac",
    "3": "fd", "fd": "fd",
}


def ex(desc: str, domain: str, omega=None, params: Optional[dict] = None,
       use_rms: bool = False, variables: Optional[Iterable[str]] = None,
       equations=None, unknowns=None, conditions=None,
       suffix: str = "ask") -> Result:
    """Run whichever analysis `domain` names -- ports `ex()`. `domain`
    is "dc"/"ac"/"fd" (or the calculator's own "1"/"2"/"3" shorthand,
    case-insensitive), matching the original's "Analysis? 1:DC 2:AC
    3:FD" prompt. Transient is deliberately absent, as it is on the
    calculator; call `tr()` directly for that. `omega` is required for
    "ac".

    The expert-mode extras mirror the original's "Add equations / Add
    unknowns / Add conditions" prompts: `equations` are joined into the
    system before solving, `unknowns` adds names to solve for (omit to
    auto-detect new symbols in the extra equations), and `conditions`
    are name=value substitutions applied at solve time (the TI's `|`
    "with" operator)."""
    key = _DOMAIN_ALIASES.get(str(domain).strip().lower())
    if key is None:
        raise ValueError(
            f"Unknown analysis domain {domain!r}; expected one of "
            f"dc/ac/fd (or 1/2/3). Expert mode has no transient option, "
            f"matching the calculator; use tr() directly."
        )
    extras = {"equations": equations, "unknowns": unknowns,
              "conditions": conditions, "suffix": suffix}
    if key == "dc":
        return dc(desc, params=params, **extras)
    if key == "ac":
        if omega is None:
            raise ValueError("ac analysis requires omega.")
        return ac(desc, omega, params=params, use_rms=use_rms, **extras)
    return fd(desc, params=params, **extras)
