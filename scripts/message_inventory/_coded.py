# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Whether an emission site is *coded*: it says a ``pitloom.messages``
message, so its line ends in `` [code]``.

A call has a *static* code when it

- is ``emit(...)``, a coded exception class (``CodedValueError(...)``,
  ``CodedImportError(...)``, ``CodedFileNotFoundError(...)``,
  ``CodedOSError(...)``, ``CodedRuntimeError(...)``,
  ``CodedTypeError(...)``), or a coded exception said again
  (``recoded(...)``, ``exc.located(...)``), or
- passes ``code=`` (or ``pitloom_code=``, as an exception class's own
  keyword) a string or a ``pitloom.messages`` constant, or
- passes ``extra=`` holding a ``pitloom_code`` key (``CODE_ATTR``), or
- passes a ``pitloom.messages`` constant (an upper-case name imported from
  that package) as an argument.

It *forwards* a code when the code is read at run time, from an exception
(``code_extra_of(exc)``, ``print_error(..., code=code_of(exc))``) or from a
record it says again (``relay_extra(...)``): the line carries the other's
code, but the site itself states no catalogued message, so it is not coded.
An ``extra=<name>`` is read through the assignments of ``<name>`` in the
site's own function (``extra = relay_extra(...)`` then ``extra=extra``),
and takes the best of them: one assignment that binds a code is enough, as
one ``None if ... else relay_extra(...)`` is, since a branch that binds
``None`` has no code to forward (it says an uncoded record again). A
stricter "every assignment" reading would only tell those two spellings
apart; it changes no site of the tree.

A site is coded (or forwards) also when it calls an in-package function or
class whose body holds such a call: a helper wrapping a coded call codes
every caller's line. A body is scanned for the direct markers only, not
through further calls, each call's ``extra=<name>`` read through the
function in the body that makes it; a body with both kinds is static.

A function that returns a coded value (``return CodedValueError(...)``)
is judged by what it returns instead: coded only when every value it
returns is (each return expression, a returned name through its
assignments, an in-package call through that function's own kind), since a
caller raising its result says whichever branch ran. ``None``, numbers and
booleans returned are no message and are not judged.

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
#: Calls that put a fixed catalogued code on a record or an exception. A
#: ``recoded(cls, exc)`` or ``exc.located(...)`` raise says a coded
#: exception again (as another class, or with its file): it refuses one
#: without a catalogued code, so its line always ends in one.
STATIC_CALLS = frozenset(
    {
        "emit",
        "CodedFileNotFoundError",
        "CodedImportError",
        "CodedOSError",
        "CodedRuntimeError",
        "CodedTypeError",
        "CodedValueError",
        "located",
        "recoded",
    }
)
#: Calls that read the code from an exception or a relayed record.
FORWARD_CALLS = frozenset({"code_extra_of", "relay_extra"})
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


#: Nodes that open a scope of their own: an assignment in one binds another
#: name than the site's.
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
#: The scopes a call's ``extra=<name>`` is read through.
_FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _assigned_values(func: ast.AST, name: str) -> list[ast.expr]:
    """The values *func*'s own body (no nested scope) assigns to *name*."""
    values: list[ast.expr] = []
    todo: list[ast.AST] = list(ast.iter_child_nodes(func))
    while todo:
        node = todo.pop()
        if isinstance(node, _SCOPES):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                values.append(node.value)
        todo.extend(ast.iter_child_nodes(node))
    return values


def _named_extra_kind(value: ast.expr, func: ast.AST | None) -> str | None:
    """The code kind of an ``extra=`` argument: of the expression itself, or,
    for a bare name, the best of the values *func* assigns to it."""
    if isinstance(value, ast.Name) and func is not None:
        return best_kind({_extra_kind(v) for v in _assigned_values(func, value.id)})
    return _extra_kind(value)


def call_code_kind(
    call: ast.Call, mod: Module, func: ast.AST | None = None
) -> str | None:
    """``STATIC``, ``FORWARD`` or ``None``: how *call* itself codes the
    message (the direct markers), an ``extra=<name>`` read through *func*,
    the function that makes the call."""
    name = callee_name(call)
    kinds: set[str | None] = set()
    if name in STATIC_CALLS:
        kinds.add(STATIC)
    if name in FORWARD_CALLS:
        kinds.add(FORWARD)
    for kw in call.keywords:
        if kw.arg in ("code", CODE_KEY):
            kinds.add(_code_kwarg_kind(kw.value, mod))
        elif kw.arg == "extra":
            kinds.add(_named_extra_kind(kw.value, func))
    if any(_is_message_constant(arg, mod) for arg in call.args):
        kinds.add(STATIC)
    return best_kind(kinds)


def _own_returns(func: ast.AST) -> list[ast.expr]:
    """The values *func*'s own body (no nested scope) returns, but for a
    constant that is not a string (``None``, a number, a boolean)."""
    values: list[ast.expr] = []
    todo: list[ast.AST] = list(ast.iter_child_nodes(func))
    while todo:
        node = todo.pop()
        if isinstance(node, _SCOPES):
            continue
        if isinstance(node, ast.Return) and node.value is not None:
            value = node.value
            if not (
                isinstance(value, ast.Constant) and not isinstance(value.value, str)
            ):
                values.append(value)
        todo.extend(ast.iter_child_nodes(node))
    return values


def worst_kind(kinds: set[str | None]) -> str | None:
    """``None`` over ``FORWARD`` over ``STATIC``: the kind every one of
    *kinds* has at least."""
    if None in kinds:
        return None
    return FORWARD if FORWARD in kinds else STATIC


def _calls_in(node: ast.AST) -> list[tuple[ast.Call, ast.AST | None]]:
    """Each call under *node*, with the innermost function that makes it
    (``None`` for a call in a top-level class body, outside any method)."""
    found: list[tuple[ast.Call, ast.AST | None]] = []
    todo: list[tuple[ast.AST, ast.AST | None]] = [
        (node, node if isinstance(node, _FUNCS) else None)
    ]
    while todo:
        parent, func = todo.pop()
        for child in ast.iter_child_nodes(parent):
            if isinstance(child, ast.Call):
                found.append((child, func))
            todo.append((child, child if isinstance(child, _FUNCS) else func))
    return found


class CodedChecker:
    """Answers "how is this site coded?" against one :class:`Index`."""

    def __init__(self, idx: Index) -> None:
        self.idx = idx
        self._memo: dict[int, str | None] = {}

    def body_kind(self, mod: Module, node: FuncNode | ast.ClassDef) -> str | None:
        """The best code kind of any call in a function or class body, an
        ``extra=<name>`` read through the function that makes the call, as
        :meth:`site_kind` reads it."""
        key = id(node)
        if key not in self._memo:
            # Read as uncoded while being judged: a helper returning its own
            # call's value does not code itself.
            self._memo[key] = None
            kind = best_kind(
                {call_code_kind(call, mod, func) for call, func in _calls_in(node)}
            )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                returned = {self._value_kind(mod, node, v) for v in _own_returns(node)}
                if returned & {STATIC, FORWARD}:
                    kind = worst_kind(returned)
            self._memo[key] = kind
        return self._memo[key]

    def _value_kind(
        self, mod: Module, func: FuncNode, value: ast.expr, follow: bool = True
    ) -> str | None:
        """How the value *func* returns is coded: a name through the values
        *func* assigns to it (one level), else the best of the calls in it,
        directly or through the in-package function or class each calls."""
        if isinstance(value, ast.Name) and follow:
            return best_kind(
                {
                    self._value_kind(mod, func, v, follow=False)
                    for v in _assigned_values(func, value.id)
                }
            )
        kinds: set[str | None] = set()
        for sub in ast.walk(value):
            if isinstance(sub, ast.Call):
                kinds.add(call_code_kind(sub, mod, func))
                found = self.idx.lookup(mod, sub.func)
                if found is not None:
                    kinds.add(self.body_kind(*found))
        return best_kind(kinds)

    def site_kind(
        self, mod: Module, call: ast.Call | None, func: ast.AST | None = None
    ) -> str | None:
        """How the site that makes *call* (in *func*) is coded, directly or
        through the in-package function or class it calls."""
        if call is None:
            return None
        kinds = {call_code_kind(call, mod, func)}
        found = self.idx.lookup(mod, call.func)
        if found is not None:
            kinds.add(self.body_kind(*found))
        return best_kind(kinds)
