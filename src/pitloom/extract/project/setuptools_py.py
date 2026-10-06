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
import math
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from pitloom.core.config import PitloomConfig
from pitloom.core.project import ProjectMetadata
from pitloom.extract.project._setuptools_options import (
    SetupOption,
    SetupOptions,
    build_setuptools_metadata,
    requirement_lines,
    shown_value,
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
            if not isinstance(k, str) or v is _UNRESOLVABLE:
                return _UNRESOLVABLE
            result[k] = v
        return result
    return _UNRESOLVABLE


#: The ``WARNING:`` tail for a ``setup()`` keyword Pitloom cannot use.
_UNDECLARED = (
    " -- treating it as undeclared and falling back to a lower-priority source"
)


def _warn_undeclared(key: str, reason: str, quiet: bool) -> None:
    if not quiet:
        log.warning("setup.py: %r %s%s", key, reason, _UNDECLARED)


def _extract_setup_kwargs(tree: ast.Module, *, quiet: bool = False) -> dict[str, Any]:
    """Extract keyword arguments from a ``setup()`` or ``setuptools.setup()`` call.

    Returns the first matching call's kwargs as a dict. A kwarg whose value
    isn't a resolvable literal (a variable, function call, ...) is omitted
    from the result -- Pitloom has no actual value to report for it, so
    treating it as "declared" would assert a confidently wrong empty
    container (e.g. ``install_requires=[]``) instead of leaving the field
    open for ``setup.cfg``'s value. A ``WARNING:`` names a dropped kwarg
    Pitloom reads (:data:`_OPTIONS`), and each ``**`` unpacking (it may hold
    one), so this isn't a silent deviation --
    unless *quiet* (default ``False``), for a caller re-reading the same
    file a second time.
    """
    node = next(iter_setup_calls(tree), None)
    if node is None:
        return {}
    kwargs: dict[str, Any] = {}
    for kw in node.keywords:
        if kw.arg is None:  # **expansion: the keywords it holds are unknown
            # Named only when a plain name: unparsing an expression recurses.
            held = kw.value.id if isinstance(kw.value, ast.Name) else "..."
            _warn_undeclared(f"**{held}", "is not read", quiet)
        else:
            value = _ast_literal(kw.value)
            if value is _UNRESOLVABLE:
                if kw.arg not in _OPTIONS:
                    continue
                _warn_undeclared(
                    kw.arg,
                    "is declared but its value isn't a statically resolvable literal",
                    quiet,
                )
                continue
            kwargs[kw.arg] = value
    return kwargs


#: A value of a type setuptools would not take for the option.
_UNREADABLE = object()


def _parse_str(raw: Any) -> Any:
    return raw.strip() if isinstance(raw, str) else _UNREADABLE


def _parse_version(raw: Any) -> Any:
    """setuptools takes a number for the version (``str(1.0)``); not one
    with no version text (``1e999``) or too long to convert."""
    if isinstance(raw, float) and not math.isfinite(raw):
        return _UNREADABLE
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        try:
            return str(raw)
        except ValueError:  # over sys.get_int_max_str_digits()
            return _UNREADABLE
    return _parse_str(raw)


def _parse_license(raw: Any) -> Any:
    """As written: the licence element builder normalises a text's ends."""
    return raw if isinstance(raw, str) else _UNREADABLE


def _parse_strings(raw: Any) -> Any:
    if not isinstance(raw, (list, tuple)) or not all(isinstance(x, str) for x in raw):
        return _UNREADABLE
    return [x.strip() for x in raw if x.strip()]


def _parse_requirements(raw: Any) -> Any:
    """A string or a list of strings, read as setuptools reads them
    (:func:`~pitloom.extract.project._setuptools_options.requirement_lines`)."""
    if isinstance(raw, str):
        return requirement_lines(raw)
    strings = _parse_strings(raw)
    return strings if strings is _UNREADABLE else requirement_lines("\n".join(raw))


def _parse_setup_keywords(raw: Any) -> Any:
    """``setup(keywords=...)`` as a list: a string is split on commas and
    whitespace."""
    if isinstance(raw, str):
        return [k.strip() for k in raw.replace(",", " ").split() if k.strip()]
    return _parse_strings(raw)


def _parse_project_urls(raw: Any) -> Any:
    if not isinstance(raw, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in raw.items()
    ):
        return _UNREADABLE
    return dict(raw)


#: setuptools option -> (its provenance's keyword, parser).
_OPTIONS: dict[str, tuple[str, Callable[[Any], Any]]] = {
    "name": ("name", _parse_str),
    "version": ("version", _parse_version),
    "description": ("description", _parse_str),
    "long_description": ("long_description", _parse_str),
    "license": ("license", _parse_license),
    "classifiers": ("classifiers", _parse_strings),
    "keywords": ("keywords", _parse_setup_keywords),
    "author": ("author", _parse_str),
    "author_email": ("author", _parse_str),
    "url": ("url", _parse_str),
    "project_urls": ("url", _parse_project_urls),
    "install_requires": ("install_requires", _parse_requirements),
    "python_requires": ("python_requires", _parse_str),
}


#: Options setuptools normalises before applying ``setup.cfg``
#: (``Distribution.__init__``): ``version=0`` is ``"0"``, given;
#: ``install_requires=["# x"]`` is ``[]``, not given.
_NORMALISED = frozenset({"version", "install_requires"})


def _option(key: str, raw: Any, quiet: bool) -> SetupOption | None:
    """*raw* as an option, or ``None``: quietly for ``None`` (setuptools'
    own "not set"), with a ``WARNING:`` when Pitloom cannot use it: of a
    type it does not read (some setuptools converts, as ``url=1``), or a
    blank string (setuptools keeps it, stating nothing)."""
    if raw is None:
        return None
    label, parse = _OPTIONS[key]
    value = parse(raw)
    if value is _UNREADABLE:
        _warn_undeclared(
            key, f"has a value Pitloom does not read ({shown_value(raw)})", quiet
        )
        return None
    if isinstance(raw, str) and raw and not raw.strip():
        _warn_undeclared(key, "is blank", quiet)
        return None
    if isinstance(value, str):
        value = value or None
    source = f"Source: setup.py | Field: setup({label}=...)"
    # setuptools normalises these before it applies setup.cfg
    given = bool(value) if key in _NORMALISED else bool(raw)
    return SetupOption(value, source, given=given)


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
    # isfile: a directory or a FIFO is none, as for setup.cfg; never raises
    if not os.path.isfile(setup_py_path):
        raise FileNotFoundError(f"setup.py not found at {setup_py_path}")
    try:
        # Bytes: the parser honours a BOM and a PEP 263 coding line.
        tree = ast.parse(setup_py_path.read_bytes(), filename="setup.py")
    # ValueError: a null byte before Python 3.12; RecursionError and
    # MemoryError: a too deeply nested expression.
    except (OSError, SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        raise ValueError(f"Could not parse setup.py: {one_line(exc)}") from exc
    kwargs = _extract_setup_kwargs(tree, quiet=quiet)
    options = {
        key: _option(key, kwargs[key], quiet) for key in _OPTIONS if key in kwargs
    }
    return {key: option for key, option in options.items() if option is not None}


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
