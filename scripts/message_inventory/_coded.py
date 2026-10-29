# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Whether an emission site is *coded*: it says a ``pitloom.messages``
message, so its line ends in `` [code]``.

A call has a *static* code when it

- is ``emit(...)``, ``code_extra(...)`` or ``CodedValueError(...)``, or
- passes ``code=`` a string or a ``pitloom.messages`` constant, or
- passes ``extra=`` holding ``code_extra(...)`` or a ``pitloom_code`` key, or
- passes a ``pitloom.messages`` constant (an upper-case name imported from
  that package) as an argument.

It *forwards* a code when the code is read from an exception at run time
(``code_extra_of(exc)``, ``print_error(..., code=code_of(exc))``): the line
carries the cause's code, but the site itself states no catalogued message,
so it is not coded.

A site is coded (or forwards) also when it calls an in-package function or
class whose body holds such a call: a helper wrapping a coded call codes
every caller's line. A body is scanned for the direct markers only, not
through further calls; a body with both kinds is static.

See also: ``_walker.py`` (sets ``coded`` and ``forwards_code`` on each record).
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from ._astutil import callee_name
from ._index import Index, Module

if TYPE_CHECKING:
    from ._index import FuncNode

STATIC = "static"
FORWARD = "forward"
#: Calls that put a fixed catalogued code on a record or an exception.
STATIC_CALLS = frozenset({"emit", "code_extra", "CodedValueError"})
#: Calls that read the code from an exception.
FORWARD_CALLS = frozenset({"code_extra_of"})
#: The ``extra`` key (and its constant) that carries a code on a log record.
CODE_KEY = "pitloom_code"
CODE_KEY_NAME = "CODE_ATTR"
MESSAGES_PACKAGE = "pitloom.messages"


def best_kind(kinds: set[str | None]) -> str | None:
    """``STATIC`` over ``FORWARD`` over ``None``."""
    if STATIC in kinds:
        return STATIC
    return FORWARD if FORWARD in kinds else None


def _is_message_constant(node: ast.AST, mod: Module) -> bool:
    if not isinstance(node, ast.Name) or not node.id.isupper():
        return False
    imported = mod.imports.get(node.id)
    return imported is not None and imported[0].startswith(MESSAGES_PACKAGE)


def _extra_kind(value: ast.expr) -> str | None:
    kinds: set[str | None] = set()
    for sub in ast.walk(value):
        if isinstance(sub, ast.Call):
            name = callee_name(sub)
            kinds.add(STATIC if name in STATIC_CALLS else None)
            kinds.add(FORWARD if name in FORWARD_CALLS else None)
        elif isinstance(sub, ast.Constant) and sub.value == CODE_KEY:
            kinds.add(STATIC)
        elif isinstance(sub, ast.Name) and sub.id == CODE_KEY_NAME:
            kinds.add(STATIC)
    return best_kind(kinds)


def _code_kwarg_kind(value: ast.expr, mod: Module) -> str | None:
    if isinstance(value, ast.Constant):
        return STATIC if isinstance(value.value, str) else None
    if any(_is_message_constant(sub, mod) for sub in ast.walk(value)):
        return STATIC
    return FORWARD


def call_code_kind(call: ast.Call, mod: Module) -> str | None:
    """``STATIC``, ``FORWARD`` or ``None``: how *call* itself codes the
    message (the direct markers)."""
    name = callee_name(call)
    kinds: set[str | None] = set()
    if name in STATIC_CALLS:
        kinds.add(STATIC)
    if name in FORWARD_CALLS:
        kinds.add(FORWARD)
    for kw in call.keywords:
        if kw.arg == "code":
            kinds.add(_code_kwarg_kind(kw.value, mod))
        elif kw.arg == "extra":
            kinds.add(_extra_kind(kw.value))
    if any(_is_message_constant(arg, mod) for arg in call.args):
        kinds.add(STATIC)
    return best_kind(kinds)


class CodedChecker:
    """Answers "how is this site coded?" against one :class:`Index`."""

    def __init__(self, idx: Index) -> None:
        self.idx = idx
        self._memo: dict[int, str | None] = {}

    def body_kind(self, mod: Module, node: FuncNode | ast.ClassDef) -> str | None:
        """The best code kind of any call in a function or class body."""
        key = id(node)
        if key not in self._memo:
            self._memo[key] = best_kind(
                {
                    call_code_kind(sub, mod)
                    for sub in ast.walk(node)
                    if isinstance(sub, ast.Call)
                }
            )
        return self._memo[key]

    def site_kind(self, mod: Module, call: ast.Call | None) -> str | None:
        """How the site that makes *call* is coded, directly or through the
        in-package function or class it calls."""
        if call is None:
            return None
        kinds = {call_code_kind(call, mod)}
        found = self.idx.lookup(mod, call.func)
        if found is not None:
            kinds.add(self.body_kind(*found))
        return best_kind(kinds)
