"""
Circuit-description parser and validator.

Ports the parsing/validation half of Symbulator: `symbv8s1` (element name
sanity check), `symbv8s2` (per-element field-count check), and `symbv8s3`
(topology validation: grounding, duplicate names, node conflicts).

Circuit description syntax (unchanged from the calculator, minus the
leading colon it required):

    "r1,1,0,1k:e1,1,0,5:c1,1,2,10'u"

Elements are separated by `:` and fields within an element by `,`. The
first character of an element's name selects its type:

    r  resistor            name,n1,n2,value
    l  inductor             name,n1,n2,value[,initial_current]
    c  capacitor             name,n1,n2,value[,initial_voltage]
    e  voltage source (indep. or dependent)   name,n1,n2,value
    j  current source (indep. or dependent)   name,n1,n2,value
    o  ideal op-amp (nullor)     name,n_plus,n_minus,n_out
    m  mutual inductance          name,Lname1,Lname2,M
    s  short circuit               name,n1,n2
    t  ideal transformer            name,n1,n2,turns1,turns2
    z,y,h,g,a,b  grounded two-port block     name,n1,n2

Node "0" is the ground/reference node.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .si_prefix import expand_shorthand

VALID_PREFIXES = "abceghjlmorstyz"

# name,n1,n2[,...]  -- total field count including the element's own name.
FIELD_COUNTS = {
    "r": 4,
    "l": 4,
    "c": 4,
    "e": 4,
    "j": 4,
    "o": 4,
    "m": 4,
    "s": 3,
    "t": 5,
    "z": 3,
    "y": 3,
    "h": 3,
    "g": 3,
    "a": 3,
    "b": 3,
}

# l/c may optionally carry one extra field -- an initial condition
# (initial inductor current / initial capacitor voltage) -- used only by
# s-domain (fd) and transient (tr) analysis; ignored in dc/ac. Unlike the
# original, which switched the *expected* field count based on which
# analysis tool was running, this port always accepts either count for
# l/c and simply treats a missing initial condition as 0.
OPTIONAL_IC_KINDS = {"l", "c"}

TWO_PORT_KINDS = set("zyghab")
GROUNDED_ELEMENT_KINDS = set("tzyghab")  # neither node may be "0"

class CircuitError(ValueError):
    """Raised for any issue found while parsing/validating a circuit."""


@dataclass
class Element:
    """One parsed circuit element -- a resistor, source, op-amp, etc.
    `fields` holds every field after the name, still as raw strings
    (nodes, values, or references to other elements depending on `kind`);
    `n1`/`n2`/`value`/`ic` below are convenience accessors into it, since
    "which field means what" differs by element kind (see FIELD_COUNTS
    and the syntax table in the module docstring)."""
    name: str            # full element name, e.g. "r1"
    kind: str             # first letter of name, e.g. "r"
    fields: List[str] = field(default_factory=list)  # fields after the name
    #: The same fields as the reader typed them, before `[a,b]` became
    #: `pr(a,b)` and `1'k` became `1*10**3`. Kept only so that a value the
    #: parser cannot read can be quoted back the way it was written; empty
    #: when nothing was rewritten. See engine's `_value`.
    raw_fields: List[str] = field(default_factory=list)

    @property
    def n1(self) -> str:
        """First node/terminal (fields[0]) -- every element kind has one
        in the same position, so this accessor is always safe to use."""
        return self.fields[0]

    @property
    def n2(self) -> str:
        """Second node/terminal (fields[1]) -- same as n1, always in the
        same position regardless of element kind."""
        return self.fields[1]

    @property
    def value(self) -> Optional[str]:
        """Raw value expression, for element kinds that have one."""
        if self.kind in ("r", "l", "c", "e", "j", "m"):
            return self.fields[2]
        return None

    @property
    def ic(self) -> str:
        """Initial condition (initial inductor current / capacitor
        voltage), for l/c elements only. "0" if not given."""
        if self.kind in OPTIONAL_IC_KINDS and len(self.fields) >= 4:
            return self.fields[3]
        return "0"


# Field indices (0-based, *after* the element name) that hold structural
# identifiers -- node names, or references to other elements. These fold
# to lowercase along with the element's own name, so `R1` and `r1` are
# one resistor and node `A` and node `a` are one node. Value fields are
# deliberately absent: case matters there ('M vs 'm, Heaviside vs
# heaviside).
_IDENTIFIER_FIELD_IDX = {
    "r": (0, 1), "l": (0, 1), "c": (0, 1), "e": (0, 1), "j": (0, 1),
    "s": (0, 1), "t": (0, 1),
    "o": (0, 1, 2),          # n+, n-, output node
    "m": (0, 1),             # the two inductors it couples
    "z": (0, 1), "y": (0, 1), "h": (0, 1), "g": (0, 1),
    "a": (0, 1), "b": (0, 1),
}


def _split_elements(desc: str) -> List[str]:
    """Break a raw circuit-description string into one raw substring per
    element, tolerating either separator style (see comment below) and
    stray leading/trailing separators or blank lines. Raises CircuitError
    if nothing is left after splitting (an empty or whitespace-only
    description)."""
    # Newlines work the same as ":" -- a circuit can be written one
    # element per line (natural in a file or a web textarea) or all on
    # one line separated by colons (the original calculator syntax).
    desc = desc.replace("\r\n", ":").replace("\r", ":").replace("\n", ":")
    desc = desc.strip()
    if desc.startswith(":"):
        desc = desc[1:]
    parts = [p.strip() for p in desc.split(":") if p.strip() != ""]
    if not parts:
        raise CircuitError("Circuit description is empty.")
    return parts


def _split_fields(raw: str) -> List[str]:
    """Split one element's raw text on `,` into fields, the way
    `str.split(",")` does -- except a comma inside parentheses doesn't
    count as a separator. Needed because the `[...]` parallel-impedance
    shortcut (see si_prefix.expand_shorthand) has already been expanded
    to `pr(a,b,c)` by the time this runs, and those inner commas belong
    to the value field, not the element's field list."""
    fields: List[str] = []
    depth = 0
    current = ""
    for ch in raw:
        if ch == "(":
            depth += 1
            current += ch
        elif ch == ")":
            depth = max(0, depth - 1)
            current += ch
        elif ch == "," and depth == 0:
            fields.append(current.strip())
            current = ""
        else:
            current += ch
    fields.append(current.strip())
    return fields


def parse_circuit(desc: str, expand_si: bool = True) -> List[Element]:
    """Parse a Symbulator-style circuit description string into a list
    of Element objects. Raises CircuitError on malformed input (mirrors
    symbv8s1 + symbv8s2).

    `expand_si=False` parses the same elements but leaves SI-prefix
    shorthand (`4.7'M`) in each field as typed, instead of expanding it
    to a literal number. Use this when the parsed elements are only
    going to be echoed back to the user (e.g. to rebuild the circuit
    description after normalizing i/I to j or resolving an ambiguous
    bare suffix) -- the SI notation is worth more to a person reading it
    back than the number it stands for, and it still gets expanded the
    normal way (`expand_si=True`, the default) at actual solve time."""
    raw_elements = _split_elements(desc)

    elements: List[Element] = []
    seen_names = set()

    for raw in raw_elements:
        typed = raw
        raw = expand_shorthand(raw, si=expand_si)
        parts = _split_fields(raw)
        typed_parts = _split_fields(typed) if typed != raw else parts
        if not parts or parts[0] == "":
            raise CircuitError(f"Malformed element description: '{raw}'.")

        # Element names, element letters and node names are all
        # case-insensitive: they fold to lowercase here so that R1 and
        # r1 are the same resistor, and node A and node a are the same
        # node. Folding before the duplicate check means writing both
        # spellings is correctly reported as a duplicate rather than
        # silently creating two elements.
        name = parts[0].lower()
        kind = name[0] if name else ""

        if kind not in VALID_PREFIXES:
            raise CircuitError(
                f"Element starting with '{kind}' not recognised. "
                f"Give element '{parts[0]}' a proper name."
            )

        # A name must survive being embedded in a symbol: the answers are
        # written as i_<name>, v_<name>, p_<name>, and a reader must be
        # able to type those inside a value or an added equation. A name
        # like `r-x` parses fine on its own, but `2*i_r-x` silently reads
        # as `2*i_r - x` and solves to an answer full of phantom symbols
        # -- so the characters that would do that are refused here, where
        # the message can still point at the right element.
        if not name.isidentifier():
            raise CircuitError(
                f"Element name '{parts[0]}' contains a character that "
                f"cannot be part of a name. Use letters, digits and "
                f"underscores, so that the element's answers (its "
                f"'i_...', 'v_...', 'p_...') can be written inside a "
                f"value or an added equation."
            )

        if name in seen_names:
            raise CircuitError(f"More than one element has been named '{name}'.")
        seen_names.add(name)

        expected = FIELD_COUNTS[kind]
        if kind in OPTIONAL_IC_KINDS or kind in TWO_PORT_KINDS:
            allowed = {expected, expected + 1}
        else:
            allowed = {expected}
        if len(parts) not in allowed:
            if kind in OPTIONAL_IC_KINDS:
                raise CircuitError(
                    f"Your description of element '{name}' has {len(parts)} terms. "
                    f"{expected} or {expected + 1} (with an initial condition) terms are "
                    f"expected for an element of type '{kind}'."
                )
            if kind in TWO_PORT_KINDS:
                raise CircuitError(
                    f"Your description of element '{name}' has {len(parts)} terms. "
                    f"{expected} terms are expected for a two-port element, or "
                    f"{expected + 1} with its parameters as the last term: "
                    f"[p11,p12,p21,p22]."
                )
            raise CircuitError(
                f"Your description of element '{name}' has {len(parts)} terms. "
                f"Exactly {expected} terms are expected for an element of type '{kind}'."
            )

        fields = list(parts[1:])
        for idx in _IDENTIFIER_FIELD_IDX.get(kind, ()):
            if idx < len(fields):
                fields[idx] = fields[idx].lower()

        # Only when the rewrite actually changed something, and only when
        # it split the same way -- a mismatch means the two cannot be lined
        # up field by field, and a wrong original is worse than none.
        raw_fields = (list(typed_parts[1:])
                      if typed != raw and len(typed_parts) == len(parts)
                      else [])
        element = Element(name=name, kind=kind, fields=fields,
                          raw_fields=raw_fields)
        if kind in TWO_PORT_KINDS and len(fields) == 3:
            two_port_param_texts(element)   # validates; raises if malformed
        elements.append(element)

    _validate_topology(elements)
    return elements


def two_port_param_texts(el: Element) -> Optional[List[str]]:
    """The four parameter expressions from a two-port element's optional
    last term, or None when the element carries only its two nodes.

    The term is written `[p11,p12,p21,p22]`; by the time fields exist,
    `expand_shorthand` has rewritten the brackets to `pr(...)` (its
    universal internal encoding of `[...]`), which is also accepted
    typed directly. Raises CircuitError when the term is not a
    four-entry list."""
    if el.kind not in TWO_PORT_KINDS or len(el.fields) < 3:
        return None
    text = el.fields[2].strip()
    shown = (el.raw_fields[2].strip()
             if len(el.raw_fields) > 2 else text)
    if not (text.startswith("pr(") and text.endswith(")")):
        raise CircuitError(
            f"The last term of two-port '{el.name}' is '{shown}'. A "
            f"two-port's parameters are written as a four-entry list: "
            f"[p11,p12,p21,p22]."
        )
    inner = text[3:-1]
    parts: List[str] = []
    depth, current = 0, ""
    for ch in inner:
        if ch == "(":
            depth += 1
            current += ch
        elif ch == ")":
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    parts.append(current.strip())
    if len(parts) != 4 or any(p == "" for p in parts):
        raise CircuitError(
            f"The parameter list of two-port '{el.name}' has "
            f"{len([p for p in parts if p])} entries. Exactly four are "
            f"expected: [p11,p12,p21,p22]."
        )
    return parts


def two_port_param_conditions(elements: List[Element]) -> List[str]:
    """The `name = value` bindings implied by every two-port parameter
    term in `elements`, ready to run through the solver's conditions
    machinery -- which is what "the values are stored in the parameter
    variables" means operationally: the same substitution the TI's `|`
    operator applied to stored variables.

    A self-referential entry (`z,1,2,[z11,z12,z21,z22]` -- the tacit
    default written out) binds nothing: the parameter is already the
    free symbol it names."""
    conds: List[str] = []
    for el in elements:
        texts = two_port_param_texts(el)
        if not texts:
            continue
        for ij, text in zip(("11", "12", "21", "22"), texts):
            name = f"{el.name}{ij}"
            if text.replace("_", "").lower() == name.replace("_", "").lower():
                continue
            conds.append(f"{name} = {text}")
    return conds


def _validate_topology(elements: List[Element], two_port_nodes: Optional[tuple] = None) -> None:
    """Whole-circuit sanity checks that can't be done element-by-element
    (ports `symbv8s3`): the circuit must be grounded (some node is 0, or
    a grounded-kind element like a two-port block is present), and no
    element may have both terminals on the same node -- a rule that
    binds even the short circuit, whose job is joining two *distinct*
    nodes: a self-loop's current enters and leaves the same KCL sum
    and so is indeterminate.

    `two_port_nodes`, when given, additionally checks that the two named
    port nodes (n1, n2) both actually appear somewhere in the circuit --
    used by tools like `equiv.port()` that ask the caller for two nodes
    by name and need to catch a typo before wasting a solve on it."""
    has_ground = False
    node1_seen = node2_seen = False
    n1_target, n2_target = (two_port_nodes or (None, None))

    for el in elements:
        if el.kind in GROUNDED_ELEMENT_KINDS:
            if el.n1 == "0" or el.n2 == "0":
                raise CircuitError(
                    f"Neither top node in element '{el.name}' can be ground."
                )

        if el.n1 == el.n2 and el.kind != "m":
            raise CircuitError(
                f"Both nodes of '{el.name}' can't be the same node."
            )

        if el.kind in GROUNDED_ELEMENT_KINDS or el.n1 == "0" or el.n2 == "0":
            has_ground = True

        if n1_target is not None:
            if el.n1 == n1_target or el.n2 == n1_target:
                node1_seen = True
            if el.n1 == n2_target or el.n2 == n2_target:
                node2_seen = True

    if two_port_nodes is None:
        if not has_ground:
            raise CircuitError("Circuit must contain a reference node 0.")
        _check_connected(elements)
    else:
        if n1_target == n2_target:
            raise CircuitError("Both nodes in the input cannot be the same node.")
        if not node1_seen:
            raise CircuitError(f"Circuit does not contain the node {n1_target} you mentioned.")
        if not node2_seen:
            raise CircuitError(f"Circuit does not contain the node {n2_target} you mentioned.")


def _check_connected(elements: List[Element]) -> None:
    """Every node must have a conduction path to the reference. A part of
    the circuit with no such path (say `r1,2,3,1` hanging on its own) has
    no defined voltages, and the solver would otherwise return it quietly
    parametrized in one of its own node voltages (`v_2 = v_3`) rather
    than flag the mistake (ports `symbv8s3`'s "floating node" check).

    Connectivity is by terminals: r/l/c/e/j/s/t join their two nodes, an
    op-amp joins all three of its terminals (its nullor constraints tie
    them together), and a grounded two-port block ties both nodes to 0.
    Mutual inductances name inductors, not nodes, so they add nothing."""
    parent = {"0": "0"}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    for el in elements:
        if el.kind == "m":
            continue
        nodes = [el.fields[i] for i in _IDENTIFIER_FIELD_IDX[el.kind]]
        if el.kind in GROUNDED_ELEMENT_KINDS:
            nodes.append("0")
        for n in nodes[1:]:
            union(nodes[0], n)

    root = find("0")
    floating = sorted(n for n in parent if find(n) != root)
    if floating:
        raise CircuitError(
            "Node(s) " + ", ".join(floating)
            + " have no path to the reference node 0; that part of the "
            "circuit is floating and its voltages are undefined."
        )


# Which field indices (0-based, after the element name) hold *values*
# (as opposed to node names / element references), per element kind.
# Used by find_ambiguous_values -- node names are never treated as
# ambiguous, so "r1,1,2k,100" with a node literally named "2k" is safe.
_VALUE_FIELD_IDX = {
    "r": (2,), "l": (2, 3), "c": (2, 3), "e": (2,), "j": (2,),
    "m": (2,), "t": (2, 3),
}


def ambiguous_in_elements(elements: List[Element]) -> List[dict]:
    """Scan parsed elements for bare engineering-notation values -- see
    find_ambiguous_values."""
    from .si_prefix import bare_suffix_match

    found: List[dict] = []
    for e in elements:
        for idx in _VALUE_FIELD_IDX.get(e.kind, ()):
            if idx >= len(e.fields):
                continue
            m = bare_suffix_match(e.fields[idx])
            if m:
                found.append({"element": e.name, "token": e.fields[idx].strip(),
                              "number": m[0], "letter": m[1]})
    return found


def find_ambiguous_values(desc: str) -> List[dict]:
    """Scan a circuit description for bare engineering-notation values
    ("1k", "4.7u") whose meaning is ambiguous between an SI unit (1'k)
    and number*variable (1*k). Returns one dict per occurrence:
    {"element", "token", "number", "letter"}. Parse errors propagate
    as CircuitError, same as parse_circuit."""
    return ambiguous_in_elements(parse_circuit(desc))
