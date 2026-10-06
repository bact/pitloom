# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python project metadata from setup.py using AST parsing.

See also: :mod:`pitloom.extract.project.setuptools_cfg` (setup.cfg parsing)
and :mod:`pitloom.extract.project.setuptools` (facade).
"""

from __future__ import annotations

import ast
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from pitloom.core.config import PitloomConfig
from pitloom.core.project import ProjectMetadata
from pitloom.extract.project._setuptools_options import (
    SetupOption,
    SetupOptions,
    build_setuptools_metadata,
)
from pitloom.logging_config import one_line

log = logging.getLogger(__name__)


def iter_setup_calls(tree: ast.AST) -> Iterator[ast.Call]:
    """Yield every ``setup()``/``x.setup()``-named call in *tree*, in
    ``ast.walk`` order -- matched on the callable's own name only (bound
    to any object, e.g. ``setuptools.setup``), not on where it's
    imported from. A caller that only wants the real setuptools call
    among several matches (e.g. an unrelated ``logger.setup()`` earlier
    in the file) must inspect the yielded calls itself; this generator
    makes no such distinction."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Name) and func.id == "setup") or (
            isinstance(func, ast.Attribute) and func.attr == "setup"
        ):
            yield node


#: Sentinel for "not a resolvable literal" (a variable, function call,
#: f-string, ...), distinct from a genuine literal ``None`` constant
#: (``Constant(value=None)``) -- conflating the two would make a real
#: ``[None]`` list element indistinguishable from an unresolvable one.
_UNRESOLVABLE = object()


def _ast_literal(node: ast.expr) -> Any:
    """Extract a Python literal value from an AST expression.

    Returns :data:`_UNRESOLVABLE` for non-literal expressions (variables,
    function calls, f-strings, etc.) rather than raising -- never ``None``
    for that case, so a genuine literal ``None`` stays distinguishable.
    """
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        # All-or-nothing, as the dict branch below: silently dropping
        # just the unresolvable elements would misrepresent a list like
        # `install_requires=[SOME_CONSTANT]` as the literal empty list
        # `[]` -- a "no dependencies" claim indistinguishable from a
        # genuinely empty `install_requires=[]`, which downstream
        # presence-based provenance treats as authoritative.
        # `_UNRESOLVABLE` here correctly propagates "not a resolvable
        # literal" instead, without colliding with a real `None` element.
        values = [_ast_literal(elt) for elt in node.elts]
        return _UNRESOLVABLE if any(v is _UNRESOLVABLE for v in values) else values
    if isinstance(node, ast.Dict):
        # All-or-nothing too: a dict missing its unresolvable entries would
        # override setup.cfg's with less than setup.py states.
        result: dict[str, Any] = {}
        for key, value in zip(node.keys, node.values, strict=False):
            if key is None:  # **unpacking
                return _UNRESOLVABLE
            k = _ast_literal(key)
            v = _ast_literal(value)
            if k is _UNRESOLVABLE or v is _UNRESOLVABLE:
                return _UNRESOLVABLE
            if isinstance(k, str):
                result[k] = v
        return result
    return _UNRESOLVABLE


def _extract_setup_kwargs(tree: ast.Module, *, quiet: bool = False) -> dict[str, Any]:
    """Extract keyword arguments from a ``setup()`` or ``setuptools.setup()`` call.

    Returns the first matching call's kwargs as a dict. A kwarg whose value
    isn't a resolvable literal (a variable, function call, ...) is omitted
    from the result -- Pitloom has no actual value to report for it, so
    treating it as "declared" would assert a confidently wrong empty
    container (e.g. ``install_requires=[]``) instead of leaving the field
    open for ``setup.cfg``'s value. A ``WARNING:`` names the dropped kwarg
    so this isn't a silent deviation -- unless *quiet* (default ``False``),
    for a caller re-reading the same file a second time.
    """
    node = next(iter_setup_calls(tree), None)
    if node is None:
        return {}
    kwargs: dict[str, Any] = {}
    for kw in node.keywords:
        if kw.arg is not None:  # skip **expansion
            value = _ast_literal(kw.value)
            if value is _UNRESOLVABLE:
                if not quiet:
                    log.warning(
                        "setup.py: %r is declared but its value isn't a"
                        " statically resolvable literal -- treating it as"
                        " undeclared and falling back to a lower-priority source",
                        kw.arg,
                    )
                continue
            kwargs[kw.arg] = value
    return kwargs


def _parse_setup_keywords(raw: Any) -> list[str]:
    """``setup(keywords=...)`` as a list: a string is split on commas and
    whitespace."""
    if isinstance(raw, str):
        return [k.strip() for k in raw.replace(",", " ").split() if k.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(k).strip() for k in raw if k]
    return []


def _parse_str(raw: Any) -> str | None:
    return raw.strip() or None if isinstance(raw, str) else None


def _parse_license(raw: Any) -> str | None:
    """As written: the licence element builder normalises a text's ends."""
    return raw if isinstance(raw, str) and raw.strip() else None


def _parse_list(raw: Any) -> list[str]:
    return [str(x).strip() for x in raw if x] if isinstance(raw, (list, tuple)) else []


def _parse_project_urls(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}


#: setuptools option -> (its provenance's keyword, parser).
_OPTIONS: dict[str, tuple[str, Callable[[Any], Any]]] = {
    "name": ("name", _parse_str),
    "version": ("version", _parse_str),
    "description": ("description", _parse_str),
    "long_description": ("long_description", _parse_str),
    "license": ("license", _parse_license),
    "classifiers": ("classifiers", _parse_list),
    "keywords": ("keywords", _parse_setup_keywords),
    "author": ("author", _parse_str),
    "author_email": ("author", _parse_str),
    "url": ("url", _parse_str),
    "project_urls": ("url", _parse_project_urls),
    "install_requires": ("install_requires", _parse_list),
    "python_requires": ("python_requires", _parse_str),
}


def read_setup_py_options(project_dir: Path, *, quiet: bool = False) -> SetupOptions:
    """The setuptools options ``setup.py``'s ``setup()`` call states as
    literals (see :func:`_extract_setup_kwargs`), ``name`` not required.

    ``quiet`` suppresses this read's own ``WARNING:`` lines (default
    ``False``) -- for a caller re-reading the same file a second time; see
    :func:`pitloom.extract.project.read_project`'s own ``quiet``.

    Raises:
        FileNotFoundError: no ``setup.py``.
        ValueError: ``setup.py`` cannot be read or parsed; one line.
    """
    setup_py_path = project_dir / "setup.py"
    if not setup_py_path.exists():
        raise FileNotFoundError(f"setup.py not found at {setup_py_path}")
    try:
        source = setup_py_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename="setup.py")
    # ValueError: undecodable bytes, or a null byte before Python 3.12.
    except (OSError, SyntaxError, ValueError) as exc:
        raise ValueError(f"Could not parse setup.py: {one_line(exc)}") from exc
    kwargs = _extract_setup_kwargs(tree, quiet=quiet)
    return {
        key: SetupOption(
            parse(kwargs[key]),
            f"Source: setup.py | Field: setup({label}=...)",
            bool(kwargs[key]),
        )
        for key, (label, parse) in _OPTIONS.items()
        if key in kwargs
    }


def read_setup_py(
    project_dir: Path,
    *,
    quiet: bool = False,
) -> tuple[ProjectMetadata, PitloomConfig]:
    """Read project metadata from ``setup.py`` alone, by
    :func:`read_setup_py_options`.

    Raises:
        FileNotFoundError: no ``setup.py``.
        ValueError: ``setup.py`` cannot be parsed, or has no literal
            ``name``.
    """
    options = read_setup_py_options(project_dir, quiet=quiet)
    metadata = build_setuptools_metadata({}, options)
    if not metadata.name:
        raise ValueError(
            "Could not extract project name from setup.py. "
            "The name= argument must be a string literal."
        )
    return metadata, PitloomConfig()
