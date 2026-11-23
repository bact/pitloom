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
  that parameter as it is (or with a URL's credentials masked by a masker
  :data:`_MASKERS` names, imported from ``pitloom.core.url_masking`` and
  bound by nothing else in the module or the method), said by
  ``print_error``: argparse wrote it, as a reader's exception is the detail
  of the line a wrapper says.

- ``exception-param``: a reporter of an exception it is handed. A
  function whose only statement (a docstring aside) is
  ``print_error(str(p), code=code_of(p))`` of its own parameter ``p`` (the
  text also as ``p`` or ``str(p) or type(p).__name__``): the text and the
  code are the exception's, whose raise is the counted site, as for
  ``exception``. A second statement, or text of its own, is a message of
  its own.
- ``prefixed``: a foreign tool's own words after Pitloom's sub-prefix (the
  ``licenseid: `` and ``fickling: `` relays). The template is a module
  constant bound to a string once in the module, then ``"%s"``; its one
  argument is ``one_line(<param>)`` of a parameter of the function saying
  it, or ``one_line(<param>, <LIMIT>)`` with ``LIMIT`` a module constant
  bound once to an ``int`` (a cut, not text), with ``one_line`` imported
  from ``pitloom.logging_config``; no keyword argument. The text is the
  tool's, the prefix only says whose.

Any of them holds only where the call is in the binder's own body (not in a
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
    from typing import TypeAlias

    from ._index import Module

    #: A function a prefixed relay is said in.
    _Function: TypeAlias = ast.FunctionDef | ast.AsyncFunctionDef

EXCEPTION = "exception"
EXCEPTION_PARAM = "exception-param"
ARGPARSE = "argparse"
PREFIXED = "prefixed"
#: Where the one-line writer of a prefixed relay's text comes from.
_ONE_LINE = ("pitloom.logging_config", "one_line")
#: The ``except`` classes that catch whatever a command raised.
_CATCH_ALL = frozenset({"Exception", "BaseException"})
_PARSER_BASES = frozenset({"argparse.ArgumentParser", "ArgumentParser"})
#: The module of the maskers an ``error`` override may wrap argparse's text
#: in, and their names there.
_MASKING_MODULE = "pitloom.core.url_masking"
_MASKERS = ("masked_given_path", "sanitize_url_credentials")
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


def _module_bindings(mod: Module, name: str) -> int:
    """How many statements of *mod*'s own body (not a nested scope's) bind
    *name*: an import, an assignment, a ``def`` or a ``class``."""
    count = 0
    for statement in mod.tree.body:
        todo: list[ast.AST] = [statement]
        while todo:
            node = todo.pop()
            count += name in _bound_names(node)
            if not isinstance(node, _SCOPES):
                todo.extend(ast.iter_child_nodes(node))
    return count


def _is_masked_param(mod: Module, func: ast.AST, text: ast.expr, param: str) -> bool:
    """*text* is the parameter *param* as it is, or the one argument of a
    masker of :data:`_MASKERS` that *mod* imports from
    :data:`_MASKING_MODULE` under its own name and that nothing else in
    *mod* or in *func* binds (a function of that name defined or assigned
    here may say anything)."""
    if unparse(text) == param:
        return True
    if not (
        isinstance(text, ast.Call)
        and isinstance(text.func, ast.Name)
        and not text.keywords
        and [unparse(arg) for arg in text.args] == [param]
    ):
        return False
    name = text.func.id
    return (
        name in _MASKERS
        and mod.imports.get(name) == (_MASKING_MODULE, name)
        and _module_bindings(mod, name) == 1
        and not any(name in _bound_names(sub) for sub in ast.walk(func))
    )


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


def _is_prefix_constant(mod: Module, node: ast.expr) -> bool:
    """*node* is a name *mod* binds once, at module level, to a string."""
    if not isinstance(node, ast.Name) or _module_bindings(mod, node.id) != 1:
        return False
    value = mod.assigns.get(node.id)
    return isinstance(value, ast.Constant) and isinstance(value.value, str)


def _is_int_constant(mod: Module, node: ast.expr) -> bool:
    """*node* is a name *mod* binds once, at module level, to an ``int``
    (never a ``bool``)."""
    if not isinstance(node, ast.Name) or _module_bindings(mod, node.id) != 1:
        return False
    value = mod.assigns.get(node.id)
    return (
        isinstance(value, ast.Constant)
        and isinstance(value.value, int)
        and not isinstance(value.value, bool)
    )


def _one_line_param(mod: Module, func: _Function, node: ast.expr) -> str:
    """The parameter of *func* that *node* writes as ``one_line(<param>)``
    or ``one_line(<param>, <LIMIT>)`` (:func:`_is_int_constant`), with
    ``one_line`` imported from ``pitloom.logging_config`` and bound by
    nothing else in *mod*; else ``""``."""
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and mod.imports.get(node.func.id) == _ONE_LINE
        and _module_bindings(mod, node.func.id) == 1
        and len(node.args) in (1, 2)
        and not node.keywords
        and isinstance(node.args[0], ast.Name)
        and all(_is_int_constant(mod, limit) for limit in node.args[1:])
    ):
        return ""
    name = node.args[0].id
    params = (*func.args.posonlyargs, *func.args.args, *func.args.kwonlyargs)
    return name if name in {a.arg for a in params} else ""


def _is_prefixed(
    mod: Module, func: ast.AST | None, call: ast.Call, text: ast.expr
) -> bool:
    """*call*, said by *func*'s own body, says ``<PREFIX> + "%s"`` with
    ``one_line(<param>)`` as its one argument, no keyword (``PREFIXED``)."""
    if (
        not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef))
        or call.keywords
        or not any(arg is text for arg in call.args)
    ):
        return False
    if not (
        isinstance(text, ast.BinOp)
        and isinstance(text.op, ast.Add)
        and _is_prefix_constant(mod, text.left)
        and isinstance(text.right, ast.Constant)
        and text.right.value == "%s"
    ):
        return False
    args = call.args[[id(arg) for arg in call.args].index(id(text)) + 1 :]
    param = _one_line_param(mod, func, args[0]) if len(args) == 1 else ""
    return bool(param) and _says_only(func.body, call, param)


def _is_exception_class(node: ast.expr | None) -> bool:
    """*node* annotates an exception: a class named ``Exception``,
    ``BaseException`` or ``...Error`` (bare or dotted), or a ``|`` union of
    such."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _is_exception_class(node.left) and _is_exception_class(node.right)
    if isinstance(node, ast.Name):
        last = node.id
    elif isinstance(node, ast.Attribute):
        last = node.attr
    else:
        return False
    return last in {"Exception", "BaseException"} or last.endswith("Error")


def _exception_param(func: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    """*name* is a parameter of *func* annotated with an exception class and
    with no default: what the caller hands it is always an exception."""
    args = func.args
    positional = (*args.posonlyargs, *args.args)
    defaulted = {a.arg for a in positional[len(positional) - len(args.defaults) :]}
    defaulted |= {
        a.arg
        for a, default in zip(args.kwonlyargs, args.kw_defaults, strict=True)
        if default is not None
    }
    return any(
        a.arg == name and a.arg not in defaulted and _is_exception_class(a.annotation)
        for a in (*positional, *args.kwonlyargs)
    )


def _is_exception_param_reporter(
    func: ast.AST | None, call: ast.Call, text: ast.expr, name: str
) -> bool:
    """*call* is the only statement of *func* (a docstring aside), *name*
    one of *func*'s parameters, an exception (:func:`_exception_param`),
    and *text* its text written by ``str()`` (``str(name)`` or ``str(name)
    or type(name).__name__``), never the bare name (``EXCEPTION_PARAM``)."""
    if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    body = func.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return (
        len(body) == 1
        and isinstance(body[0], ast.Expr)
        and body[0].value is call
        and unparse(text) != name
        and _exception_param(func, name)
    )


def relay_kind(
    mod: Module,
    site: tuple[str, ast.Call | None, ast.expr | None],
    func: ast.AST | None,
    cls: str | None,
) -> str | None:
    """``EXCEPTION``, ``EXCEPTION_PARAM``, ``ARGPARSE``, ``PREFIXED`` or
    ``None`` for the site *site* (emitter, call, text argument) in *func* of
    class *cls*."""
    emitter, call, text = site
    if text is None or call is None:
        return None
    if emitter != "print_error":
        return PREFIXED if _is_prefixed(mod, func, call, text) else None
    param = _parser_error_param(mod, func, cls)
    if (
        param
        and isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _is_masked_param(mod, func, text, param)
        and _says_only(func.body, call, param)
    ):
        return ARGPARSE
    name = _forwarded(call)
    if name is None or not _is_own_text(text, name):
        return None
    if _caught_by_catch_all(func, call, name):
        return EXCEPTION
    if _is_exception_param_reporter(func, call, text, name):
        return EXCEPTION_PARAM
    return None
