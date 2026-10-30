# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``[project.optional-dependencies]`` added to a settled dependency list.

A ``[project]`` reader builds its metadata with the base
``dependencies`` only, fills gaps from ``[tool.poetry]``
(:func:`~pitloom.core.project.merge_project_metadata`), then calls
:func:`add_optional_dependencies`. The base list and the extras each come
from the table that declares them, as Poetry reads a ``[project]`` with
``dynamic = ["dependencies"]``: extras in the list before the merge would
make it non-empty, and a non-empty list wins the merge whole.

See also: :func:`pitloom.core.requirements.flatten_optional_dependencies`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import (
    parse_provenance_value,
    provenance_segment,
    provenance_source,
)
from pitloom.core.requirements import flatten_optional_dependencies

OPTIONAL_DEPENDENCIES_FIELD = "project.optional-dependencies"


def add_optional_dependencies(
    metadata: ProjectMetadata,
    optional: Mapping[str, Iterable[str]] | None,
    *,
    declared: bool,
    source: str,
    quiet: bool = False,
    field: str = OPTIONAL_DEPENDENCIES_FIELD,
) -> None:
    """Append *optional* to *metadata*'s dependencies, tagged as a built
    wheel's ``Requires-Dist`` has them, self-references expanded.

    *declared*: *field*, the extras' table, is in the raw data, even
    empty; the ``dependencies`` provenance then names it, next to the
    field and *source* (``Source: <file>``) the base list came from. The
    ``WARNING:`` for an entry that cannot be used names *field* without
    its ``project.`` prefix; *quiet* silences it.
    """
    metadata.dependencies = flatten_optional_dependencies(
        metadata.dependencies,
        optional,
        metadata.name,
        source=field.removeprefix("project."),
        quiet=quiet,
    )
    if declared:
        prior = metadata.provenance.get("dependencies")
        entry = parse_provenance_value(prior) if prior else {}
        own = parse_provenance_value(source)["source"]
        sources = dict.fromkeys(s for s in (entry.get("source"), own) if s)
        fields = dict.fromkeys(f for f in (entry.get("location"), field) if f)
        metadata.provenance["dependencies"] = provenance_segment(
            provenance_source(", ".join(sources)), "Field", ", ".join(fields)
        )
