# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Lint: no broad handler in ``src/pitloom`` swallows an
:class:`~pitloom.core.internal_error.InternalError`.

An ``InternalError`` is a ``ValueError``, so a handler catching
``ValueError``, ``Exception``, ``BaseException`` (alone or in a tuple) or
anything at all would report a bug in Pitloom as a user's bad file, a
skipped field or a debug line. Each such handler must:

- (i) follow an ``except InternalError`` clause of the same ``try``;
- (ii) start with ``reraise_internal(<its name>)``;
- (iii) end in a bare ``raise`` or ``raise <its name>``; or
- (iv) be on :data:`_ALLOWED`, with the reason it may not re-raise.

A ``contextlib.suppress`` of a broad type swallows as a handler does: it
must be on :data:`_ALLOWED_SUPPRESS`. A stale entry of either list fails.

See also: :func:`pitloom.core.internal_error.reraise_internal`.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from pitloom.core.internal_error import InternalError, reraise_internal

_SRC = Path(__file__).parent.parent.parent / "src" / "pitloom"

#: The classes an ``InternalError`` is an instance of, but for itself.
_BROAD = frozenset({"ValueError", "Exception", "BaseException"})

#: (file relative to src/pitloom, enclosing function) -> why its broad
#: handlers may let an ``InternalError`` go.
_ALLOWED: dict[tuple[str, str], str] = {}

#: (file relative to src/pitloom, enclosing function) -> why its broad
#: ``contextlib.suppress`` may swallow an ``InternalError``.
_ALLOWED_SUPPRESS: dict[tuple[str, str], str] = {}


def _caught(node: ast.expr | None) -> set[str]:
    """The class names an ``except`` clause's type names (``*`` for bare)."""
    if node is None:
        return {"*"}
    if isinstance(node, ast.Tuple):
        return set().union(*(_caught(element) for element in node.elts))
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    return {"?"}  # a computed type: reviewed by hand (none today)


def _is_broad(names: set[str]) -> bool:
    return bool(names & (_BROAD | {"*", "?"}))


def _exempt(handlers: list[ast.ExceptHandler], index: int) -> bool:
    """Exemptions (i) to (iii) for ``handlers[index]``."""
    handler = handlers[index]
    if any("InternalError" in _caught(h.type) for h in handlers[:index]):
        return True
    first, last = handler.body[0], handler.body[-1]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Call)
        and isinstance(first.value.func, ast.Name)
        and first.value.func.id == "reraise_internal"
        and len(first.value.args) == 1
        and isinstance(first.value.args[0], ast.Name)
        and first.value.args[0].id == handler.name
    ):
        return True
    return isinstance(last, ast.Raise) and (
        last.exc is None
        or (isinstance(last.exc, ast.Name) and last.exc.id == handler.name)
    )


def _functions(tree: ast.Module) -> dict[ast.AST, str]:
    """Each node of *tree* -> the name of its innermost enclosing function
    (``<module>`` outside any)."""
    owner: dict[ast.AST, str] = {}

    def visit(node: ast.AST, name: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = (
                child.name
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                else name
            )
            owner[child] = inner
            visit(child, inner)

    visit(tree, "<module>")
    return owner


def _sites(src: Path) -> Iterator[tuple[str, str, int, str]]:
    """(kind, file, line, function) of each broad handler or suppress in
    *src* that exemptions (i) to (iii) do not cover."""
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(src).as_posix()
        tree = ast.parse(path.read_bytes(), filename=rel)
        owner = _functions(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for index, handler in enumerate(node.handlers):
                    if _is_broad(_caught(handler.type)) and not _exempt(
                        node.handlers, index
                    ):
                        yield "handler", rel, handler.lineno, owner[handler]
            elif (
                isinstance(node, ast.Call)
                and (getattr(node.func, "id", None) or getattr(node.func, "attr", None))
                == "suppress"
                and any(_is_broad(_caught(arg)) for arg in node.args)
            ):
                yield "suppress", rel, node.lineno, owner[node]


def test_no_broad_handler_swallows_an_internal_error() -> None:
    unlisted = [
        f"{rel}:{line} ({function}): {kind}"
        for kind, rel, line, function in _sites(_SRC)
        if (rel, function)
        not in (_ALLOWED if kind == "handler" else _ALLOWED_SUPPRESS)
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


_CASES = {
    "value-error": "try:\n    f()\nexcept ValueError:\n    pass\n",
    "tuple": "try:\n    f()\nexcept (OSError, ValueError):\n    pass\n",
    "exception": "try:\n    f()\nexcept Exception:\n    pass\n",
    "base": "try:\n    f()\nexcept BaseException:\n    pass\n",
    "bare": "try:\n    f()\nexcept:\n    pass\n",
    "dotted": "try:\n    f()\nexcept builtins.Exception:\n    pass\n",
    "wrong-name": (
        "try:\n    f()\nexcept ValueError as exc:\n"
        "    reraise_internal(other)\n"
    ),
    "not-first": (
        "try:\n    f()\nexcept ValueError as exc:\n"
        "    log(exc)\n    reraise_internal(exc)\n"
    ),
    "raise-other": (
        "try:\n    f()\nexcept ValueError as exc:\n    raise Coded() from exc\n"
    ),
    "guard-after": (
        "try:\n    f()\nexcept ValueError:\n    pass\n"
        "except InternalError:\n    raise\n"
    ),
    "suppress": "with suppress(ValueError):\n    f()\n",
    "suppress-dotted": "with contextlib.suppress(OSError, Exception):\n    f()\n",
}

_CLEAN = {
    "narrow": "try:\n    f()\nexcept (OSError, KeyError):\n    pass\n",
    "guard": (
        "try:\n    f()\nexcept InternalError:\n    raise\n"
        "except ValueError:\n    pass\n"
    ),
    "helper": (
        "try:\n    f()\nexcept ValueError as exc:\n"
        "    reraise_internal(exc)\n    pass\n"
    ),
    "bare-raise": "try:\n    f()\nexcept Exception:\n    log()\n    raise\n",
    "raise-name": (
        "try:\n    f()\nexcept Exception as exc:\n    log()\n    raise exc\n"
    ),
    "suppress-narrow": "with suppress(OSError):\n    f()\n",
}


def _write(tmp_path: Path, text: str) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "m.py").write_text(f"def g():\n{_indent(text)}", encoding="utf-8")
    return src


def _indent(text: str) -> str:
    return "".join(f"    {line}\n" for line in text.splitlines())


@pytest.mark.parametrize("text", _CASES.values(), ids=_CASES.keys())
def test_the_lint_finds_a_swallowing_handler(tmp_path: Path, text: str) -> None:
    found = list(_sites(_write(tmp_path, text)))
    assert [(rel, function) for _, rel, _, function in found] == [("m.py", "g")]


@pytest.mark.parametrize("text", _CLEAN.values(), ids=_CLEAN.keys())
def test_the_lint_passes_a_guarded_handler(tmp_path: Path, text: str) -> None:
    assert not list(_sites(_write(tmp_path, text)))


def test_reraise_internal() -> None:
    bug = InternalError("a bug")
    with pytest.raises(InternalError) as caught:
        reraise_internal(bug)
    assert caught.value is bug
    for other in (ValueError("bad input"), OSError("gone"), KeyboardInterrupt()):
        reraise_internal(other)  # returns: not a bug of Pitloom's
