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
returns is, since a caller raising its result says whichever branch ran.
Each return expression is split into the values it may give (both arms of
``a if c else b``, each operand of ``a or b``), a returned name into each
value assigned to it (one level), and each such value is coded by the best
of the calls in it, an in-package call through that function's own kind.
``None``, numbers and booleans are no message and are not judged; nor is a
call back into a function still being judged (recursion): its kind is what
its other returns make it.

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


def _is_no_message(value: ast.expr) -> bool:
    """Whether *value* is a constant that is not a string (``None``, a
    number, a boolean): no message, not judged."""
    return isinstance(value, ast.Constant) and not isinstance(value.value, str)


def _own_returns(func: ast.AST) -> list[ast.expr]:
    """The values *func*'s own body (no nested scope) returns."""
    values: list[ast.expr] = []
    todo: list[ast.AST] = list(ast.iter_child_nodes(func))
    while todo:
        node = todo.pop()
        if isinstance(node, _SCOPES):
            continue
        if isinstance(node, ast.Return) and node.value is not None:
            values.append(node.value)
        todo.extend(ast.iter_child_nodes(node))
    return values


def _branches(value: ast.expr) -> list[ast.expr]:
    """The values *value* may give: both arms of a conditional expression,
    each operand of ``and``/``or``, recursively; but for those of
    :func:`_is_no_message`."""
    if isinstance(value, ast.IfExp):
        return _branches(value.body) + _branches(value.orelse)
    if isinstance(value, ast.BoolOp):
        return [b for operand in value.values for b in _branches(operand)]
    return [] if _is_no_message(value) else [value]


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
        #: The functions being judged, by key, each with its depth on the
        #: stack, and per depth the lowest depth its judgement read.
        self._open: dict[int, int] = {}
        self._low: list[int] = []

    def body_kind(self, mod: Module, node: FuncNode | ast.ClassDef) -> str | None:
        """The best code kind of any call in a function or class body, an
        ``extra=<name>`` read through the function that makes the call, as
        :meth:`site_kind` reads it; a function returning a coded value by
        the worst of its returns. A judgement that read a function still
        being judged further out is not kept: it holds only for that one."""
        key = id(node)
        if key in self._memo:
            return self._memo[key]
        depth = len(self._low)
        self._open[key] = depth
        self._low.append(depth)
        try:
            kind = best_kind(
                {call_code_kind(call, mod, func) for call, func in _calls_in(node)}
            )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                returned: set[str | None] = set()
                for value in _own_returns(node):
                    returned |= self._value_kinds(mod, node, value)
                if returned & {STATIC, FORWARD}:
                    kind = worst_kind(returned)
        finally:
            del self._open[key]
            low = self._low.pop()
        if low < depth:
            self._low[-1] = min(self._low[-1], low)
        else:
            self._memo[key] = kind
        return kind

    def _value_kinds(
        self, mod: Module, func: FuncNode, value: ast.expr, follow: bool = True
    ) -> set[str | None]:
        """The code kind of each value *func* may return in *value*
        (:func:`_branches`), a name through each value *func* assigns to it
        (one level); empty when none is judged."""
        kinds: set[str | None] = set()
        for branch in _branches(value):
            if isinstance(branch, ast.Name) and follow:
                assigned = _assigned_values(func, branch.id)
                if not assigned:
                    kinds.add(None)
                for v in assigned:
                    kinds |= self._value_kinds(mod, func, v, follow=False)
            else:
                kinds |= self._branch_kind(mod, func, branch)
        return kinds

    def _branch_kind(
        self, mod: Module, func: FuncNode, branch: ast.expr
    ) -> set[str | None]:
        """The best of the calls in *branch*, directly or through the
        in-package function or class each calls; empty (not judged) when it
        has none but a call back into a function being judged."""
        kinds: set[str | None] = set()
        recursive = False
        for sub in ast.walk(branch):
            if not isinstance(sub, ast.Call):
                continue
            kinds.add(call_code_kind(sub, mod, func))
            found = self.idx.lookup(mod, sub.func)
            if found is None:
                continue
            depth = self._open.get(id(found[1]))
            if depth is None:
                kinds.add(self.body_kind(*found))
            else:
                recursive = True
                self._low[-1] = min(self._low[-1], depth)
        best = best_kind(kinds)
        return set() if best is None and recursive else {best}

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
