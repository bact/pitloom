# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One ``[tool.poetry.dependencies]`` table as the PEP 508 requirement
poetry-core writes for it in a wheel's ``Requires-Dist``.

poetry-core's own code converts the version constraint (``^1.0`` is
``>=1.0,<2.0``), the per-dependency ``extras`` (``name[a,b]``, canonical
and sorted), a ``git`` or ``url`` source (``name @ git+https://...@rev``)
and the ``python`` and ``platform`` keys (``python_version``/
``python_full_version`` and ``sys_platform`` markers). The ``markers``,
``python`` and ``platform`` markers are joined with ``and`` in that order,
as poetry-core joins them, through
:func:`~pitloom.core.requirements.add_marker`; poetry-core also simplifies
the joined marker (``python_version >= "3.8"`` and ``python = ">=3.9"``
become ``python_version >= "3.9"``), Pitloom keeps both terms.

See also: :mod:`pitloom.extract.project.poetry` (the caller) and
:mod:`pitloom.extract.project._poetry_extras`.
"""

from __future__ import annotations

from typing import Any

from poetry.core.constraints.generic import parse_constraint as parse_generic
from poetry.core.constraints.version import parse_constraint
from poetry.core.factory import Factory
from poetry.core.packages.utils.utils import create_nested_marker
from poetry.core.version.markers import parse_marker as poetry_marker

from pitloom.core.pep508 import parse_requirement
from pitloom.core.requirements import (
    add_marker,
    normalize_dependency_specifier,
    warn_skipped_dependency,
)
from pitloom.logging_config import one_line

#: Characters of a conversion error a ``WARNING:`` shows.
_SHOWN_CHARS = 200
#: Keys naming a local source, which poetry-core writes as a ``file://``
#: URL of the build machine.
_LOCAL_SOURCES = ("path", "file")
#: Keys of a dependency table that are not part of its base requirement.
_NOT_BASE = ("markers", "python", "platform", "optional")


def poetry_requirement(
    name: str, constraint: Any, *, quiet: bool = False
) -> str | None:
    """*constraint*, one Poetry dependency table (or version string) of
    *name*, as a PEP 508 requirement, its name canonicalised.

    Returns ``None``, with a ``WARNING:`` naming *name*, for a ``path``
    (or ``file``) source, which is not portable, and for a table
    poetry-core cannot read or that is not valid PEP 508.
    """
    if isinstance(constraint, dict):
        local = next((key for key in _LOCAL_SOURCES if key in constraint), None)
        if local is not None:
            warn_skipped_dependency(
                "Poetry", name, f"a local {local} source is not portable", quiet=quiet
            )
            return None
    try:
        req = parse_requirement(_base_requirement(name, constraint), quiet=quiet)
        for marker in _markers(constraint):
            add_marker(req, marker)
    except (ValueError, TypeError, AttributeError) as exc:
        reason = f"not convertible to PEP 508: {one_line(exc, _SHOWN_CHARS)}"
        warn_skipped_dependency("Poetry", name, reason, quiet=quiet)
        return None
    return normalize_dependency_specifier(str(req))


def _base_requirement(name: str, constraint: Any) -> str:
    """poetry-core's requirement for *constraint* without its marker.

    Raises:
        ValueError: poetry-core cannot parse a constraint or source.
        TypeError, AttributeError: a key has a type poetry-core rejects.
    """
    if isinstance(constraint, dict):
        constraint = {k: v for k, v in constraint.items() if k not in _NOT_BASE}
    return str(Factory.create_dependency(name, constraint).base_pep_508_name)


def _markers(constraint: Any) -> list[str]:
    """The ``markers``, ``python`` and ``platform`` markers of
    *constraint*, in poetry-core's order; an empty key adds none.

    Raises:
        ValueError: poetry-core cannot parse the ``python`` or
            ``platform`` constraint.
        TypeError: ``markers`` is not a string.
        AttributeError: ``python`` or ``platform`` is not a string.
    """
    if not isinstance(constraint, dict):
        return []
    markers = constraint.get("markers")
    if markers is not None and not isinstance(markers, str):
        raise TypeError(f"'markers' is {type(markers).__name__}, expected a string")
    found = [markers] if markers else []
    if python := constraint.get("python"):
        found.append(_simplified("python_version", parse_constraint(python)))
    if platform := constraint.get("platform"):
        found.append(_simplified("sys_platform", parse_generic(platform)))
    return [marker for marker in found if marker]


def _simplified(name: str, constraint: Any) -> str:
    """The marker of *constraint* on *name* as poetry-core writes it:
    its own text (``create_nested_marker``) re-read by its marker parser,
    which simplifies it (``python_version >= "3.9" and python_version <
    "3.10"`` is ``python_version == "3.9"``); ``""`` for any version. The
    text is poetry-core's, never the project's, so its nesting is
    bounded."""
    text = create_nested_marker(name, constraint)
    return str(poetry_marker(text)) if text else ""
