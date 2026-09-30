# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Type checks for the ``[tool.poetry]`` keys
:mod:`pitloom.extract.project.poetry` reads.

A present key of the wrong type (``version = 3``) is treated as absent,
with one ``WARNING:`` naming the key and the file; an absent key stays
silent.

See also: :mod:`pitloom.extract.project.poetry` (the extractor).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _is_str(value: Any) -> bool:
    return isinstance(value, str)


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(_is_str(v) for v in value)


def _is_str_or_str_list(value: Any) -> bool:
    return _is_str(value) or _is_str_list(value)


def is_table(value: Any) -> bool:
    """Return whether *value* is a TOML table."""
    return isinstance(value, dict)


#: Accepted shape of each ``[tool.poetry]`` key this extractor reads, with
#: the phrase naming it in the wrong-type warning.
_FIELD_SHAPES: dict[str, tuple[Callable[[Any], bool], str]] = {
    "name": (_is_str, "a string"),
    "version": (_is_str, "a string"),
    "description": (_is_str, "a string"),
    "readme": (_is_str_or_str_list, "a string or list of strings"),
    "license": (_is_str, "a string"),
    "authors": (_is_str_list, "a list of strings"),
    "keywords": (_is_str_list, "a list of strings"),
    "homepage": (_is_str, "a string"),
    "repository": (_is_str, "a string"),
    "documentation": (_is_str, "a string"),
    "dependencies": (is_table, "a table"),
}


def read_poetry_section(
    data: dict[str, Any], pyproject_path: Path, *, quiet: bool = False
) -> Any:
    """Return the raw ``[tool.poetry]`` value, or ``None`` when absent.

    The value is not type-checked. A ``[tool]`` that is not a table warns
    once and counts as absent.
    """
    tool = data.get("tool", {})
    if not is_table(tool):
        got = type(tool).__name__
        warn_wrong_type(pyproject_path, "[tool]", got, "a table", quiet=quiet)
        return None
    return tool.get("poetry")


def drop_wrong_typed_fields(
    poetry: dict[str, Any], pyproject_path: Path, *, quiet: bool
) -> dict[str, Any]:
    """Return a copy of *poetry* without its wrong-typed metadata keys.

    A key whose value does not match :data:`_FIELD_SHAPES` is treated as
    absent, with one ``WARNING:`` naming the key and the file; an absent
    key stays silent.
    """
    kept = dict(poetry)
    for key, (has_shape, expected) in _FIELD_SHAPES.items():
        if key in poetry and not has_shape(poetry[key]):
            where = f"[tool.poetry] '{key}'"
            # A shape that accepts an empty list expects a list of strings.
            got = _describe(poetry[key], list_expected=has_shape([]))
            warn_wrong_type(pyproject_path, where, got, expected, quiet=quiet)
            del kept[key]
    return kept


def warn_wrong_type(
    pyproject_path: Path, where: str, got: str, expected: str, *, quiet: bool
) -> None:
    """Warn that the value at *where* (e.g. ``[tool.poetry] 'version'``),
    described by *got*, is ignored for having the wrong type."""
    if not quiet:
        log.warning(
            "%s: %s is %s, expected %s -- ignoring it",
            pyproject_path,
            where,
            got,
            expected,
        )


def _describe(value: Any, *, list_expected: bool) -> str:
    """Name *value*'s type; when a list was expected, name the first
    non-string item that made the list wrong instead."""
    bad = [v for v in value if not _is_str(v)] if isinstance(value, list) else []
    if list_expected and bad:
        return f"a list with a non-string item ({type(bad[0]).__name__})"
    return type(value).__name__
