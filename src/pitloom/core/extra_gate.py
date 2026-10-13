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
from typing import TypeAlias

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

__all__ = ["Gate", "MarkerShapeError", "is_extra_gated", "parse_gate"]

#: The extras a requirement is gated by, or ``None`` when it is required
#: (no extra gate). Never empty.
Gate: TypeAlias = "frozenset[str] | None"

_TOKEN = re.compile(
    r"""\s*(?:"[^"]*"|'[^']*'|===|==|!=|~=|<=|>=|<|>|\(|\)|[A-Za-z_][\w.]*)"""
)


class MarkerShapeError(ValueError):
    """The marker's extra gate cannot be isolated from its other terms."""


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
        extra_gates = [gate for gate in gates if gate is not None]
        if len(extra_gates) > 1:
            raise MarkerShapeError("extra and extra")
        return extra_gates[0] if extra_gates else None

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


def parse_gate(marker: str) -> Gate:
    """The extra gate of a requirement whose marker reads *marker*:
    ``None`` when it names no extra.

    Raises:
        MarkerShapeError: the gate cannot be isolated (``extra == "a" or
            python_version < "3.9"``, ``extra != "x"``); the caller
            records the requirement as required.
    """
    return _GateParser(marker).parse()


def is_extra_gated(req: Requirement) -> bool:
    """Whether *req* belongs to an extra only: its marker's gate isolates
    (:func:`parse_gate`); one that cannot is required."""
    try:
        return req.marker is not None and parse_gate(str(req.marker)) is not None
    except MarkerShapeError:
        return False
