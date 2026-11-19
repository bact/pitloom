# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``[tool.poetry.dependencies]`` as PEP 508 requirements plus
``requires-python``, and Poetry's version constraints (``^``, ``~``) as
PEP 440.

See also: :mod:`pitloom.extract.project.poetry` (the caller) and
:mod:`pitloom.extract.project._poetry_requirements` (one dependency table).
"""

from __future__ import annotations

from functools import partial
from typing import Any

from packaging.utils import canonicalize_name

from pitloom.core.requirements import flatten_optional_dependencies
from pitloom.extract.project._poetry_extras import (
    extras_requirements,
    requirements_per_table,
)
from pitloom.extract.project._poetry_requirements import poetry_requirement


def parse_poetry_deps(
    deps: Any,
    *,
    extras: Any = None,
    project_name: str | None = None,
    quiet: bool = False,
    warn_unlisted: bool = True,
) -> tuple[list[str], str | None, bool]:
    """Convert ``[tool.poetry.dependencies]`` to a PEP 508 list plus requires-python.

    The ``python`` key is extracted as ``requires_python`` (matched
    case-insensitively); every other entry becomes the requirement
    poetry-core writes for it
    (:func:`~pitloom.extract.project._poetry_requirements.poetry_requirement`),
    one per table of the list form, each with its own marker. An entry
    with every table ``optional = true`` is listed once per extra of
    *extras* (``[tool.poetry.extras]``, extra name to dependency names,
    matched by canonical name) that names it, tagged ``extra == "x"``;
    named by no extra, it is dropped with a ``WARNING:``
    unless *warn_unlisted* is false (the extras were already reported as
    ignored). A list with required tables gives those as base
    requirements, its optional tables only to an extra that names it. A
    requirement on *project_name* in an extra is expanded
    (:func:`~pitloom.core.requirements.flatten_optional_dependencies`).

    Returns:
        ``(dependencies, requires_python, python_declared)`` --
        ``requires_python`` may be ``None`` when the ``python`` key is
        absent OR when it's present but resolves to no constraint (e.g.
        ``python = "*"``); ``python_declared`` distinguishes those two
        cases so a caller can gate provenance on presence, not on
        ``requires_python``'s truthiness -- an explicit "no constraint"
        is a genuine, authoritative answer that
        :func:`pitloom.core.project.merge_project_metadata` must not
        silently override from a lower-priority source, the same
        None-vs-absent distinction already applied to container fields.
    """
    if not isinstance(deps, dict):
        return [], None, False

    requires_python: str | None = None
    python_declared = False
    base: list[tuple[str, str]] = []  # (canonical name, PEP 508 string)
    # canonical name -> (declared name, PEP 508 strings), every dependency
    entries: dict[str, tuple[str, list[str]]] = {}
    optional: set[str] = set()

    for pkg, constraint in deps.items():
        if pkg.lower() == "python":
            requires_python = _poetry_constraint_to_pep440(constraint)
            python_declared = True
            continue
        every, required = requirements_per_table(
            constraint, partial(poetry_requirement, pkg, quiet=quiet)
        )
        if not every:
            continue
        key = canonicalize_name(pkg)
        entries[key] = (pkg, every)
        base += [(key, dep) for dep in required]
        if not required:
            optional.add(key)

    by_extra, listed = extras_requirements(
        extras, entries, optional, deps, quiet=quiet, warn_unlisted=warn_unlisted
    )
    return (
        flatten_optional_dependencies(
            [dep for key, dep in base if key not in listed],
            by_extra,
            project_name,
            source="Poetry",
            quiet=quiet,
        ),
        requires_python,
        python_declared,
    )


def _convert_caret(ver: str) -> str:
    """Convert a Poetry caret constraint (without the ``^``) to PEP 440."""
    parts = ver.split(".")
    try:
        major = int(parts[0])
        if major > 0:
            return f">={ver},<{major + 1}.0.0"
        if len(parts) > 1:
            minor = int(parts[1])
            return f">={ver},<0.{minor + 1}.0"
        return f">={ver}"
    except (ValueError, IndexError):
        return f">={ver}"


def _convert_tilde(ver: str) -> str:
    """Convert a Poetry tilde constraint (without the ``~``) to PEP 440."""
    parts = ver.split(".")
    try:
        if len(parts) >= 2:
            major = int(parts[0])
            minor = int(parts[1])
            return f">={ver},<{major}.{minor + 1}.0"
        return f">={ver}"
    except (ValueError, IndexError):
        return f">={ver}"


def _poetry_constraint_to_pep440(constraint: Any) -> str | None:
    """Convert a Poetry version constraint to a PEP 440 specifier string.

    Handles ``^X.Y.Z``, ``~X.Y.Z``, ``*``, and plain PEP 440 specifiers.
    Returns ``None`` for ``*`` or unrecognised input.
    """
    if isinstance(constraint, dict):
        constraint = constraint.get("version", "*")
    if not isinstance(constraint, str):
        return None
    constraint = constraint.strip()
    if not constraint or constraint == "*":
        return None

    # Bare version (no operator): Poetry treats "X.Y.Z" as exact (==X.Y.Z).
    if constraint[0].isdigit():
        return f"=={constraint}"

    if constraint.startswith("^"):
        return _convert_caret(constraint[1:])

    if constraint.startswith("~"):
        return _convert_tilde(constraint[1:])

    return str(constraint)
