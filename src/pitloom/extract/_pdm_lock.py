# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for resolved dependencies from a PDM ``pdm.lock``.

See also: :mod:`pitloom.extract._poetry_lock` (the ``poetry.lock``
extractor this module mirrors in shape -- same ``groups``-based
main/default filtering, same source-stage-only scoping, same
``name==version`` output, same "no silent deviations" warning policy)
and :mod:`pitloom.extract._locked_dependencies` (the cascade module that
calls this extractor and overlays its output onto
``ProjectMetadata.locked_dependencies``, in priority order against every
other lock format).

``pdm.lock`` is source-stage-only, the same class as every sibling lock
format: appropriate for ``loom project``/``loom generate``, never for
``loom wheel``/``embed-wheel`` (the real wheel's own metadata is ground
truth and never consults a lock) or ``loom env`` (live introspection of
what's actually installed is strictly more authoritative than a lock
that may be stale relative to it).

Unlike ``uv.lock``, a ``pdm.lock`` resolves one Python-compatibility
range per file (its own ``metadata.targets``), not a whole matrix of
marker branches in one flat table -- so it has nothing structurally
equivalent to ``uv.lock``'s "the same name pinned at two genuinely
different versions" case. The same package name *can* still appear more
than once, but only to record separate per-extra variants (e.g. a bare
``httpx`` entry alongside an ``httpx`` entry with ``extras = ["socks"]``)
that always agree on ``version`` -- collapsed here via
:func:`pitloom.extract._lock_common.group_versions_by_canonical_name`,
also shared with :mod:`pitloom.extract._requirements_txt`. Only a name
whose entries actually *disagree* on version is treated as ambiguous and
skipped, matching ``uv.lock``'s "don't guess" policy for that case.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pitloom.extract._lock_common import (
    find_first_present_key,
    group_versions_by_canonical_name,
    is_usable_version,
    load_lock_toml,
    warn_non_registry_source,
)

log = logging.getLogger(__name__)

__all__ = ["extract_pdm_lock_dependencies"]

#: The default (main/runtime) group name in a ``pdm.lock``'s per-package
#: ``groups`` list -- PDM's equivalent of ``poetry.lock``'s ``"main"``.
_DEFAULT_GROUP = "default"

#: ``pdm.lock`` keys, present directly on a ``[[package]]`` table (no
#: nested ``source`` table, unlike ``uv.lock``), that mark a package as
#: not resolvable to a meaningful PyPI version pin. ``url`` records a
#: direct file-server/URL-sourced package (PDM's ``static_urls`` lock
#: strategy, or a plain ``pdm add <url>``) -- confirmed absent from
#: every ordinary registry-resolved entry in this repo's two real
#: pdm.lock fixtures, so including it here doesn't risk excluding a
#: normal package.
_NON_REGISTRY_KEYS = ("git", "url", "path")


def _default_group_package_or_none(pkg: object) -> dict[str, Any] | None:
    """Return *pkg* itself when it's a well-formed, default-group,
    registry-sourced, versioned ``[[package]]`` entry -- ``None``
    otherwise (with a ``WARNING:`` for anything malformed or
    non-registry-sourced; silent for a package that's simply not in the
    default group, the same "expected filtering" as ``poetry.lock``'s
    non-``main`` group exclusion)."""
    if not isinstance(pkg, dict):
        log.warning(
            "Skipping malformed pdm.lock [[package]] entry: expected a table, got %s",
            type(pkg).__name__,
        )
        return None
    name = pkg.get("name")
    if not isinstance(name, str) or not name:
        log.warning(
            "Skipping malformed pdm.lock [[package]] entry: missing or "
            "non-string 'name' (name=%r)",
            name,
        )
        return None

    groups = pkg.get("groups", [_DEFAULT_GROUP])
    if not isinstance(groups, list) or _DEFAULT_GROUP not in groups:
        return None

    non_registry_key = find_first_present_key(pkg, _NON_REGISTRY_KEYS)
    if non_registry_key is not None:
        warn_non_registry_source("pdm.lock", name, non_registry_key)
        return None

    version = pkg.get("version")
    if not is_usable_version(version):
        log.warning(
            "Skipping pdm.lock entry %r: missing or non-string 'version'",
            name,
        )
        return None
    return pkg


def extract_pdm_lock_dependencies(project_dir: Path) -> list[str]:
    """Read ``pdm.lock`` next to ``pyproject.toml`` and return its
    resolved ``default``-group packages as exact-pin PEP 508 strings.

    Returns an empty list when no ``pdm.lock`` is present, or when it
    can't be parsed -- this is optional enrichment, never a requirement.
    """
    lock_path = project_dir / "pdm.lock"
    data = load_lock_toml(lock_path)
    if data is None:
        return []

    packages = data.get("package", [])
    if not isinstance(packages, list):
        log.warning(
            "%s: top-level 'package' key is %s, expected a list -- ignoring pdm.lock",
            lock_path,
            type(packages).__name__,
        )
        return []

    default_group_packages = [
        pkg
        for pkg in (_default_group_package_or_none(raw) for raw in packages)
        if pkg is not None
    ]

    pairs = [(pkg["name"], pkg["version"]) for pkg in default_group_packages]

    dependencies: list[str] = []
    for group in group_versions_by_canonical_name(pairs).values():
        name, version = group[0]
        conflicting_versions = {v for _, v in group}
        if len(conflicting_versions) > 1:
            log.warning(
                "Skipping pdm.lock entry %r: pinned to conflicting versions (%s)",
                name,
                ", ".join(sorted(conflicting_versions)),
            )
            continue
        dependencies.append(f"{name}=={version}")
    return dependencies
