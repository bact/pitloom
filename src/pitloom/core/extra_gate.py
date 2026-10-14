# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The extra gate of a requirement: the extras its marker requires, read
from the marker's text, never by evaluating it, so the result does not
depend on the machine that builds the SBOM.

The one rule deciding whether a declared dependency belongs to an extra:
the edge kind (:mod:`pitloom.assemble.spdx3._dep_scope`) and the lock
pins asked for the project's extras
(:mod:`pitloom.extract.lock._extra_pins`) both read it here.
"""

from __future__ import annotations

import re
from typing import NamedTuple, TypeAlias

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from pitloom.core.pep508 import MAX_MARKER_NESTING, marker_nesting

__all__ = [
    "Gate",
    "GateReading",
    "MarkerShapeError",
    "is_extra_gated",
    "parse_gate",
    "read_gate",
]

#: The extras a requirement is gated by, or ``None`` when it is required
#: (no extra gate). Never empty.
Gate: TypeAlias = "frozenset[str] | None"

_TOKEN = re.compile(
    r"""\s*(?:"[^"]*"|'[^']*'|===|==|!=|~=|<=|>=|<|>|\(|\)|[A-Za-z_][\w.]*)"""
)


class MarkerShapeError(ValueError):
    """The marker's extra gate cannot be isolated from its other terms."""


class GateReading(NamedTuple):
    """A marker's extra gate, and the extras an ``and`` requires together."""

    gate: Gate
    #: The extras of every ``and`` requiring two or more different extras
    #: at once (``extra == "x" and extra == "dev"``: a requirement with an
    #: extra marker of its own, declared in another extra); empty if none.
    #: Each such ``and`` gates by any of its extras, the condition that
    #: they hold together ignored.
    joined: frozenset[str]


# pylint: disable-next=too-few-public-methods
class _GateParser:
    """Recursive-descent reader of a marker's text: ``or`` of ``and`` of
    comparisons or parenthesised sub-markers."""

    def __init__(self, marker: str) -> None:
        text = marker.strip()
        self._tokens: list[str] = []
        pos = 0
        while pos < len(text):
            match = _TOKEN.match(text, pos)
            if match is None:
                raise MarkerShapeError(text)
            self._tokens.append(match.group().strip())
            pos = match.end()
        self._pos = 0
        self.joined: set[str] = set()

    def parse(self) -> Gate:
        """The whole marker's gate."""
        gate = self._or()
        if self._pos != len(self._tokens):
            raise MarkerShapeError(self._tokens[self._pos])
        return gate

    def _peek(self) -> str | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _next(self) -> str:
        token = self._peek()
        if token is None:
            raise MarkerShapeError("unexpected end")
        self._pos += 1
        return token

    def _or(self) -> Gate:
        gates = [self._and()]
        while self._peek() == "or":
            self._pos += 1
            gates.append(self._and())
        extra_gates = [gate for gate in gates if gate is not None]
        if not extra_gates:
            return None
        if len(extra_gates) != len(gates):
            # e.g. `extra == "a" or python_version < "3.9"`
            raise MarkerShapeError("extra or non-extra")
        return frozenset().union(*extra_gates)

    def _and(self) -> Gate:
        gates = [self._atom()]
        while self._peek() == "and":
            self._pos += 1
            gates.append(self._atom())
        extra_gates = {gate for gate in gates if gate is not None}
        if not extra_gates:
            return None
        union: frozenset[str] = frozenset().union(*extra_gates)
        if len(extra_gates) > 1:
            self.joined |= union
        return union

    def _atom(self) -> Gate:
        if self._peek() == "(":
            self._pos += 1
            gate = self._or()
            if self._next() != ")":
                raise MarkerShapeError("unbalanced parenthesis")
            return gate
        lhs, op = self._next(), self._next()
        if op == "not":
            op = f"not {self._next()}"
        rhs = self._next()
        if "extra" not in (lhs, rhs):
            return None
        value = rhs if lhs == "extra" else lhs
        if op != "==" or value[:1] not in ('"', "'"):
            raise MarkerShapeError(f"{lhs} {op} {rhs}")
        if not value[1:-1].strip():
            raise MarkerShapeError("empty extra name")
        return frozenset({canonicalize_name(value[1:-1])})


def read_gate(marker: str) -> GateReading:
    """The extra gate of a requirement whose marker reads *marker*
    (``None`` when it names no extra), and the extras an ``and`` requires
    together (:attr:`GateReading.joined`): ``extra == "x" and extra ==
    "dev"`` is gated by ``dev`` and ``x``, as an ``or`` of them.

    Raises:
        MarkerShapeError: the gate cannot be isolated (``extra == "a" or
            python_version < "3.9"``, ``extra != "x"``), or *marker* nests
            over :data:`~pitloom.core.pep508.MAX_MARKER_NESTING`; the
            caller records the requirement as required.
    """
    if marker_nesting(marker, marker=True) > MAX_MARKER_NESTING:
        raise MarkerShapeError("nested too deep")
    parser = _GateParser(marker)
    try:
        gate = parser.parse()
    except RecursionError as exc:
        raise MarkerShapeError("nested too deep") from exc
    return GateReading(gate, frozenset(parser.joined))


def parse_gate(marker: str) -> Gate:
    """The extra gate of :func:`read_gate`.

    Raises:
        MarkerShapeError: as :func:`read_gate`.
    """
    return read_gate(marker).gate


def is_extra_gated(req: Requirement) -> bool:
    """Whether *req* belongs to an extra only: its marker's gate isolates
    (:func:`parse_gate`); one that cannot is required."""
    try:
        return req.marker is not None and parse_gate(str(req.marker)) is not None
    except MarkerShapeError:
        return False
