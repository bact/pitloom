# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Sites that say no text of their own: they relay another's, known by the
shape of the code around the call, never by a variable's name.

- ``exception``: the catch-all handler's line. In ``except Exception as e``
  (or ``BaseException``), ``print_error(str(e), code=code_of(e))``, the text
  also as ``e`` or ``str(e) or type(e).__name__``: the text and the code are
  the caught exception's, whose raise is the counted site. A narrower
  ``except``, or a line adding text of its own, is a message of its own.
- ``argparse``: ``argparse``'s own refusal. In the ``error(self, message)``
  method of a class deriving from ``argparse.ArgumentParser``, the text is
  that parameter as it is, said by ``print_error``: argparse wrote it, as a
  reader's exception is the detail of the line a wrapper says.

Either holds only where the call is in the binder's own body (not in a
nested function, lambda, class or comprehension) and nothing in that body
binds the name again (an assignment, ``del``, a parameter, an inner
``except ... as``, a loop or ``with`` target, an import, a ``match``
capture, ``global``/``nonlocal``): else the text may be the site's own.

See also: ``_scope.py`` (both are out of scope), ``_walker_calls.py`` (sets
``relays`` on each record).
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from ._astutil import callee_name, unparse

if TYPE_CHECKING:
    from ._index import Module

EXCEPTION = "exception"
ARGPARSE = "argparse"
#: The ``except`` classes that catch whatever a command raised.
_CATCH_ALL = frozenset({"Exception", "BaseException"})
_PARSER_BASES = frozenset({"argparse.ArgumentParser", "ArgumentParser"})
#: Nodes that open a scope of their own: a call inside one is not said by
#: the binder's body, whatever names it reads.
_SCOPES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.ClassDef,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


def _is_str_of(node: ast.expr, name: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and callee_name(node) == "str"
        and len(node.args) == 1
        and not node.keywords
        and unparse(node.args[0]) == name
    )


def _is_own_text(node: ast.expr, name: str) -> bool:
    """*node* is exception *name*'s own text: ``name``, ``str(name)`` or
    ``str(name) or type(name).__name__``."""
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return (
            len(node.values) == 2
            and _is_str_of(node.values[0], name)
            and unparse(node.values[1]) == f"type({name}).__name__"
        )
    return unparse(node) == name or _is_str_of(node, name)


def _forwarded(call: ast.Call) -> str | None:
    """The exception named by ``code=code_of(<name>)``, else ``None``."""
    for kw in call.keywords:
        value = kw.value
        if (
            kw.arg == "code"
            and isinstance(value, ast.Call)
            and callee_name(value) == "code_of"
            and len(value.args) == 1
            and isinstance(value.args[0], ast.Name)
        ):
            return value.args[0].id
    return None


def _bound_names(node: ast.AST) -> set[str]:
    """The names *node* itself binds, deletes or declares."""
    if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
        return {node.id}  # assignment, augmented, for, with-as, walrus, del
    if isinstance(node, ast.alias):
        return {node.asname or node.name.split(".")[0]}
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return set(node.names)
    if isinstance(node, ast.arg):
        return {node.arg}
    # A def, a class, an ``except ... as``, a match capture, star or rest.
    found = getattr(node, "name", None) or getattr(node, "rest", None)
    return {found} if isinstance(found, str) else set()


def _in_own_scope(body: list[ast.stmt], call: ast.Call) -> bool:
    """Whether *call* is in *body* outside any nested scope (:data:`_SCOPES`)."""
    todo: list[ast.AST] = list(body)
    while todo:
        node = todo.pop()
        if node is call:
            return True
        if not isinstance(node, _SCOPES):
            todo.extend(ast.iter_child_nodes(node))
    return False


def _says_only(body: list[ast.stmt], call: ast.Call, name: str) -> bool:
    """*call* is said by *body* itself, and nothing in *body*, nested scopes
    too, binds *name* again."""
    rebound = any(name in _bound_names(sub) for st in body for sub in ast.walk(st))
    return not rebound and _in_own_scope(body, call)


def _caught_by_catch_all(func: ast.AST | None, call: ast.Call, name: str) -> bool:
    """*call* is said by the body of an ``except Exception as <name>`` of
    *func* (:func:`_says_only`)."""
    if func is None:
        return False
    for handler in ast.walk(func):
        if (
            isinstance(handler, ast.ExceptHandler)
            and handler.name == name
            and handler.type is not None
            and unparse(handler.type) in _CATCH_ALL
            and _says_only(handler.body, call, name)
        ):
            return True
    return False


def _parser_error_param(mod: Module, func: ast.AST | None, cls: str | None) -> str:
    """The message parameter of *func* when it is the ``error`` override of
    an ``argparse.ArgumentParser`` subclass, else ``""``."""
    node = mod.classes.get(cls or "")
    if (
        node is None
        or not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef))
        or func.name != "error"
        or func not in node.body
        or len(func.args.args) != 2
    ):
        return ""
    if not any(unparse(base) in _PARSER_BASES for base in node.bases):
        return ""
    return func.args.args[1].arg


def relay_kind(
    mod: Module,
    site: tuple[str, ast.Call | None, ast.expr | None],
    func: ast.AST | None,
    cls: str | None,
) -> str | None:
    """``EXCEPTION``, ``ARGPARSE`` or ``None`` for the site *site*
    (emitter, call, text argument) in *func* of class *cls*."""
    emitter, call, text = site
    if text is None:
        return None
    if emitter != "print_error" or call is None:
        return None
    param = _parser_error_param(mod, func, cls)
    if (
        param
        and isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef))
        and unparse(text) == param
        and _says_only(func.body, call, param)
    ):
        return ARGPARSE
    name = _forwarded(call)
    if (
        name is not None
        and _is_own_text(text, name)
        and _caught_by_catch_all(func, call, name)
    ):
        return EXCEPTION
    return None
