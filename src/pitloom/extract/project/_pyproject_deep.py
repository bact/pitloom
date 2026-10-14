# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``[project]`` requirements nesting over the marker-nesting cap, held out
of ``pyproject-metadata``'s parse and put back after it.

``pyproject-metadata`` parses every requirement with ``packaging``, where
a ``RecursionError`` would fail the whole read; held out, such a
requirement reaches the shared parse
(:func:`pitloom.core.pep508.parse_requirement`) as on every other route.

See also: :mod:`pitloom.extract.project.pyproject`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pitloom.core.pep508 import is_over_nesting_cap

__all__ = ["HeldRequirements", "hold_deep_requirements"]


@dataclass
class HeldRequirements:
    """The requirements held out, by their index in their list."""

    dependencies: dict[int, str] = field(default_factory=dict)
    #: By extra, as declared.
    optional: dict[str, dict[int, str]] = field(default_factory=dict)

    def restore_dependencies(self, parsed: list[str]) -> list[str]:
        """*parsed*, the ``dependencies`` parsed, with the held ones back."""
        return _restored(parsed, self.dependencies)

    def restore_optional(self, parsed: dict[str, list[str]]) -> dict[str, list[str]]:
        """*parsed*, the ``optional-dependencies`` parsed, with the held
        ones back."""
        return {
            extra: _restored(texts, self.optional.get(extra, {}))
            for extra, texts in parsed.items()
        }


def hold_deep_requirements(
    data: dict[str, Any], *, quiet: bool = False
) -> tuple[dict[str, Any], HeldRequirements]:
    """*data* without its ``[project]`` requirements over the cap, each
    with one ``WARNING:`` (:func:`~pitloom.core.pep508.is_over_nesting_cap`,
    silent when *quiet*), and those held. A field of another shape is
    left as is, for ``pyproject-metadata`` to report. *data* holds a
    ``[project]`` table."""
    project: dict[str, Any] = data["project"]
    held = HeldRequirements()
    kept = dict(project)
    dependencies = project.get("dependencies")
    if isinstance(dependencies, list):
        kept["dependencies"] = _held(dependencies, held.dependencies, quiet)
    optional = project.get("optional-dependencies")
    if isinstance(optional, dict):
        kept["optional-dependencies"] = {
            extra: (
                _held(texts, held.optional.setdefault(extra, {}), quiet)
                if isinstance(texts, list)
                else texts
            )
            for extra, texts in optional.items()
        }
    return {**data, "project": kept}, held


def _held(entries: list[Any], held: dict[int, str], quiet: bool) -> list[Any]:
    """*entries* without the strings over the cap, added to *held*."""
    kept = []
    for index, entry in enumerate(entries):
        if isinstance(entry, str) and is_over_nesting_cap(entry, quiet=quiet):
            held[index] = entry
        else:
            kept.append(entry)
    return kept


def _restored(parsed: list[str], held: dict[int, str]) -> list[str]:
    """*parsed* with each *held* entry back at its index."""
    restored = list(parsed)
    for index in sorted(held):
        restored.insert(index, held[index])
    return restored
