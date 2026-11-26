# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Lint: no broad handler in ``src/pitloom`` swallows an
:class:`~pitloom.core.internal_error.InternalError`.

An ``InternalError`` is a ``ValueError``, so a handler whose types catch
one (``ValueError``, ``Exception``, ``BaseException``, a tuple or constant
holding one, or a bare ``except``) would report a bug in Pitloom as a
user's bad file, a skipped field or a debug line. The types are resolved
in the module's own namespace, so a constant such as ``_READ_ERRORS`` is
seen through. In each ``try``, the first clause that catches one must:

- (ii) start with ``reraise_internal(<its name>)``;
- (iii) end in a bare ``raise`` or ``raise <its name>`` (the name not bound
  again), with no ``return``, ``break`` or ``continue`` before it;
- (v) end so in ``raise InternalError(...)`` (it adds context to the bug); or
- (iv) be on :data:`_ALLOWED`, with the reason it may not re-raise.

A later clause of that ``try`` never sees one (i). A ``contextlib.suppress``
of such a type swallows as a handler does: it must be on
:data:`_ALLOWED_SUPPRESS`. A stale entry of either list fails.

See also: :func:`pitloom.core.internal_error.reraise_internal`,
``tests/core/test_internal_error_routes.py`` (the routes, run).
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import importlib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, TypeGuard

import pytest

from pitloom.core.internal_error import InternalError, reraise_internal

_SRC = Path(__file__).parent.parent.parent / "src" / "pitloom"

_LOGGING = (
    "never raises: it runs inside a logging call, which would print a raise "
    "as '--- Logging error ---' and drop the record"
)
_HELD = (
    "cleanup that re-raises later: the first exception is held while the "
    "process tree is killed and reaped, then raised by the caller (a second "
    "one, an InternalError too, is dropped for the first)"
)
_ARGPARSE = (
    "an argparse type= callable: argparse turns any ValueError it raises into "
    "'invalid ... value' (exit 2), so re-raising changes nothing"
)

#: (file relative to src/pitloom, enclosing function's qualified name) ->
#: why its broad handlers may let an ``InternalError`` go.
_ALLOWED: dict[tuple[str, str], str] = {
    ("cli/commands/utils.py", "cli_error_handler.wrapper"): (
        "cli_error_handler: the top-level reporter every command's error "
        "reaches; it reports a bug as an ERROR: line and exits"
    ),
    ("log_masking.py", "masked_text"): (
        "a masker never fails open: on any failure it says a fixed text, "
        "never the raw one (it also runs inside logging calls)"
    ),
    ("log_masking.py", "mask_third_party_record"): _LOGGING,
    ("log_masking.py", "_set_unformatted"): _LOGGING,
    ("log_masking.py", "_mask_message"): _LOGGING,
    ("log_masking.py", "_mask_trace"): _LOGGING,
    ("log_masking.py", "mask_record"): _LOGGING,
    ("core/_models_wheel_build_kill.py", "kill_process_tree"): _HELD,
    ("core/_models_wheel_build_kill.py", "_kill_windows_tree"): _HELD,
    ("core/_models_wheel_build_kill.py", "_hold"): _HELD,
    ("core/_models_wheel_build_kill.py", "_reap"): _HELD,
    ("extract/_usage_parse.py", "_hooked_call"): (
        "runs while a trace or profile hook may be set: a Python call here is "
        "one a hook can abort, which would skip the retry and the fallback; "
        "an InternalError of the call itself already re-raises (begun())"
    ),
    ("extract/_usage_parse.py", "_hooked_outcome"): (
        "a thread's entry: it puts the exception in its outcome, and "
        "parse_python raises it again in the caller's thread"
    ),
    ("extract/remote/_git_redirect.py", "_probe_within.ask"): (
        "a thread's entry: it puts the InternalError in its answer, and "
        "_probe_within raises it again in the caller's thread"
    ),
    ("core/temp_dirs.py", "rmtree_quietly"): (
        "never raises by contract: it runs from signal handlers, "
        "weakref.finalize and finally blocks"
    ),
    ("core/_models_wheel_build_and_read.py", "_remove_work_dir"): (
        "a cleanup callback: a raise first would skip the rmtree fallback "
        "and the left-behind warning"
    ),
    ("core/_models_wheel_setuptools.py", "_isolated_sys_modules"): (
        "a loop in a finally: a raise mid-loop leaves project modules in "
        "sys.modules and replaces the exception already in flight"
    ),
    ("core/_models_wheel_unlistable.py", "_audit"): (
        "an audit hook: a raise fails the audited call inside a build "
        "backend; its body calls the standard library only"
    ),
    ("core/build_signals.py", "TerminationGuard._arm"): (
        "signal.signal only, and the installed list must still be popped"
    ),
    ("core/build_signals.py", "TerminationGuard._restore"): (
        "cleanup in the signal path's finally and __exit__: a raise would "
        "leave Pitloom's handlers installed"
    ),
    ("cli/_id_args.py", "namespace_arg"): _ARGPARSE,
    ("cli/_parser_credentials.py", "fingerprint_argument"): _ARGPARSE,
    ("cli/options.py", "_build_timeout_arg"): _ARGPARSE,
    ("cli/options.py", "_flag_integer"): (
        "int(text) only, for the argparse type= callables byte_budget and "
        "positive_byte_ceiling"
    ),
}

#: Packages (relative to src/pitloom) that import nothing of Pitloom's, so
#: no ``InternalError`` is raised inside them (``tests/extract/ai_model/
#: formats/test_isolation.py`` holds that).
_PITLOOM_FREE = ("extract/ai_model/formats/",)

#: (file relative to src/pitloom, enclosing function's qualified name) ->
#: why its broad ``contextlib.suppress`` may swallow an ``InternalError``.
_ALLOWED_SUPPRESS: dict[tuple[str, str], str] = {
    ("core/build_signals.py", "TerminationGuard._terminate"): (
        "a signal handler: a raise would skip raise_signal, so the process "
        "would not die by the signal"
    ),
    ("core/build_signals.py", "TerminationGuard._run_cleanups"): (
        "every cleanup must run, from a signal handler or an __exit__ with "
        "an exception in flight"
    ),
}

#: The classes an ``InternalError`` is an instance of, but for itself.
_SUPERCLASSES = frozenset(
    kind.__name__ for kind in InternalError.__mro__[1:] if kind is not object
)

#: A module's namespace, to resolve an ``except`` type in.
Namespace = Callable[[str], dict[str, Any]]


def _module_namespace(rel: str) -> dict[str, Any]:
    """The namespace of ``src/pitloom/<rel>``, imported."""
    dotted = "pitloom." + rel.removesuffix(".py").replace("/", ".")
    return vars(importlib.import_module(dotted.removesuffix(".__init__")))


def _catches(node: ast.expr | None, namespace: dict[str, Any]) -> bool:
    """Whether an ``except`` clause of type *node* (``None``: bare) catches
    an ``InternalError``."""
    if node is None:
        return True
    try:
        # pylint: disable-next=eval-used
        value = eval(  # nosec B307 - a type expression of Pitloom's own source
            compile(ast.Expression(node), "<except>", "eval"), dict(namespace)
        )
    except NameError:  # a local (a lazily imported module's class): by name
        leaves = {
            getattr(leaf, "id", None) or getattr(leaf, "attr", None)
            for leaf in (node.elts if isinstance(node, ast.Tuple) else [node])
        }
        return bool(leaves & _SUPERCLASSES)
    kinds = value if isinstance(value, tuple) else (value,)
    return any(issubclass(InternalError, kind) for kind in kinds)


def _exits_early(handler: ast.ExceptHandler) -> bool:
    """Whether *handler* can leave before its last statement: a ``return``,
    ``break`` or ``continue`` of its own (not of a nested function)."""
    stack: list[ast.AST] = list(handler.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.Return, ast.Break, ast.Continue)):
            return True
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(node))
    return False


def _ends_in_raise(handler: ast.ExceptHandler) -> bool:
    """Exemptions (iii) and (v), for a handler that cannot leave before it."""
    last = handler.body[-1]
    if not isinstance(last, ast.Raise) or _exits_early(handler):
        return False
    if last.exc is None:
        return True
    if isinstance(last.exc, ast.Name):
        return last.exc.id == handler.name and not any(
            isinstance(node, ast.Name)
            and node.id == handler.name
            and isinstance(node.ctx, ast.Store)
            for node in ast.walk(handler)
        )
    return (
        isinstance(last.exc, ast.Call)
        and isinstance(last.exc.func, ast.Name)
        and last.exc.func.id == "InternalError"
    )


def _starts_with_helper(handler: ast.ExceptHandler) -> bool:
    """Exemption (ii)."""
    first = handler.body[0]
    return (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Call)
        and isinstance(first.value.func, ast.Name)
        and first.value.func.id == "reraise_internal"
        and len(first.value.args) == 1
        and isinstance(first.value.args[0], ast.Name)
        and first.value.args[0].id == handler.name
    )


def _functions(tree: ast.Module) -> dict[ast.AST, str]:
    """Each node of *tree* -> the qualified name of its innermost enclosing
    function (``cli_error_handler.wrapper``; ``<module>`` outside any)."""
    owner: dict[ast.AST, str] = {}
    scopes = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

    def visit(node: ast.AST, path: tuple[str, ...], name: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner_path, inner = path, name
            if isinstance(child, scopes):
                inner_path = (*path, child.name)
                if not isinstance(child, ast.ClassDef):
                    inner = ".".join(inner_path)
            owner[child] = inner
            visit(child, inner_path, inner)

    visit(tree, (), "<module>")
    return owner


def _is_suppress(node: ast.AST) -> TypeGuard[ast.Call]:
    return isinstance(node, ast.Call) and "suppress" in (
        getattr(node.func, "id", None),
        getattr(node.func, "attr", None),
    )


def _sites(
    src: Path, namespace_of: Namespace = _module_namespace
) -> Iterator[tuple[str, str, int, str]]:
    """(kind, file, line, function) of each handler or ``suppress`` in *src*
    that lets an ``InternalError`` go and no exemption (i) to (iii) or (v)
    covers."""
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(src).as_posix()
        if rel.startswith(_PITLOOM_FREE):
            continue
        tree = ast.parse(path.read_bytes(), filename=rel)
        nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Try) or _is_suppress(n)]
        if not nodes:
            continue
        namespace, owner = namespace_of(rel), _functions(tree)
        for node in nodes:
            if isinstance(node, ast.Try):
                first = next(
                    (h for h in node.handlers if _catches(h.type, namespace)), None
                )
                if first and not (_starts_with_helper(first) or _ends_in_raise(first)):
                    yield "handler", rel, first.lineno, owner[first]
            elif _is_suppress(node) and any(
                _catches(arg, namespace) for arg in node.args
            ):
                yield "suppress", rel, node.lineno, owner[node]


def test_no_broad_handler_swallows_an_internal_error() -> None:
    unlisted = [
        f"{rel}:{line} ({function}): {kind}"
        for kind, rel, line, function in _sites(_SRC)
        if (rel, function) not in (_ALLOWED if kind == "handler" else _ALLOWED_SUPPRESS)
    ]
    assert unlisted == [], (
        "start each handler with reraise_internal(exc), or add it to "
        "_ALLOWED with the reason:\n" + "\n".join(unlisted)
    )


def test_no_allowlist_entry_is_stale() -> None:
    seen = {(kind, rel, function) for kind, rel, _, function in _sites(_SRC)}
    stale = [
        key
        for kind, table in (("handler", _ALLOWED), ("suppress", _ALLOWED_SUPPRESS))
        for key in table
        if (kind, *key) not in seen
    ]
    assert stale == []


_ERRORS = (OSError, ValueError)
_NARROW = (OSError, KeyError)

_CASES = {
    "value-error": "try:\n    f()\nexcept ValueError:\n    pass\n",
    "tuple": "try:\n    f()\nexcept (OSError, ValueError):\n    pass\n",
    "constant": "try:\n    f()\nexcept _ERRORS:\n    pass\n",
    "exception": "try:\n    f()\nexcept Exception:\n    pass\n",
    "base": "try:\n    f()\nexcept BaseException:\n    pass\n",
    "bare": "try:\n    f()\nexcept:\n    pass\n",
    "dotted": "try:\n    f()\nexcept builtins.Exception:\n    pass\n",
    "wrong-name": (
        "try:\n    f()\nexcept ValueError as exc:\n    reraise_internal(other)\n"
    ),
    "not-first": (
        "try:\n    f()\nexcept ValueError as exc:\n"
        "    log(exc)\n    reraise_internal(exc)\n"
    ),
    "raise-other": (
        "try:\n    f()\nexcept ValueError as exc:\n    raise Coded() from exc\n"
    ),
    "raise-other-name": ("try:\n    f()\nexcept ValueError as exc:\n    raise other\n"),
    "raise-rebound": (
        "try:\n    f()\nexcept ValueError as exc:\n    exc = Coded()\n    raise exc\n"
    ),
    "raise-after-return": (
        "try:\n    f()\nexcept ValueError as exc:\n"
        "    if c:\n        return None\n    raise\n"
    ),
    "raise-after-continue": (
        "for x in y:\n    try:\n        f()\n    except ValueError:\n"
        "        if c:\n            continue\n        raise\n"
    ),
    "guard-after": (
        "try:\n    f()\nexcept ValueError:\n    pass\n"
        "except InternalError:\n    raise\n"
    ),
    "second-clause": (
        "try:\n    f()\nexcept KeyError:\n    raise\nexcept ValueError:\n    pass\n"
    ),
    "suppress": "with suppress(ValueError):\n    f()\n",
    "suppress-dotted": "with contextlib.suppress(OSError, Exception):\n    f()\n",
    "local-name": "try:\n    f()\nexcept (lib.Error, ValueError):\n    pass\n",
}

_CLEAN = {
    "narrow": "try:\n    f()\nexcept (OSError, KeyError):\n    pass\n",
    "narrow-constant": "try:\n    f()\nexcept _NARROW:\n    pass\n",
    "guard": (
        "try:\n    f()\nexcept InternalError:\n    raise\n"
        "except ValueError:\n    pass\n"
    ),
    "earlier-broad": (
        "try:\n    f()\nexcept ValueError:\n    raise\nexcept Exception:\n    pass\n"
    ),
    "helper": (
        "try:\n    f()\nexcept ValueError as exc:\n"
        "    reraise_internal(exc)\n    pass\n"
    ),
    "bare-raise": "try:\n    f()\nexcept Exception:\n    log()\n    raise\n",
    "raise-name": (
        "try:\n    f()\nexcept Exception as exc:\n    log()\n    raise exc\n"
    ),
    "raise-internal": (
        "try:\n    f()\nexcept ValueError as exc:\n"
        "    raise InternalError('context') from exc\n"
    ),
    "nested-return": (
        "try:\n    f()\nexcept ValueError:\n    def h():\n        return 1\n    raise\n"
    ),
    "no-handler": "try:\n    f()\nfinally:\n    g()\n",
    "suppress-narrow": "with suppress(OSError):\n    f()\n",
    "local-narrow": "try:\n    f()\nexcept lib.ValueErrorLike:\n    pass\n",
}

_NAMES: dict[str, Any] = {
    "builtins": builtins,
    "contextlib": contextlib,
    "InternalError": InternalError,
    "_ERRORS": _ERRORS,
    "_NARROW": _NARROW,
}


def _write(tmp_path: Path, text: str) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    body = "".join(f"    {line}\n" for line in text.splitlines())
    (src / "m.py").write_text(f"def g():\n{body}", encoding="utf-8")
    return src


@pytest.mark.parametrize("text", _CASES.values(), ids=_CASES.keys())
def test_the_lint_finds_a_swallowing_handler(tmp_path: Path, text: str) -> None:
    found = list(_sites(_write(tmp_path, text), lambda _: _NAMES))
    assert [(rel, function) for _, rel, _, function in found] == [("m.py", "g")]


@pytest.mark.parametrize("text", _CLEAN.values(), ids=_CLEAN.keys())
def test_the_lint_passes_a_guarded_handler(tmp_path: Path, text: str) -> None:
    assert not list(_sites(_write(tmp_path, text), lambda _: _NAMES))


def test_reraise_internal() -> None:
    bug = InternalError("a bug")
    with pytest.raises(InternalError) as caught:
        reraise_internal(bug)
    assert caught.value is bug
    for other in (ValueError("bad input"), OSError("gone"), KeyboardInterrupt()):
        reraise_internal(other)  # returns: not a bug of Pitloom's
