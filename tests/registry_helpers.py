# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Build a Loom ID registry for a test without hand-writing its JSON.

See also: :mod:`pitloom.id_registry` (the registry), tests/id_registry/
(its own tests).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from pitloom.id_registry import IdRegistry, RegistryEntry
from pitloom.id_registry._types import _element_key

#: ``(compact type, name) -> (spdxId, sha256 or None)``.
Entries = Mapping[tuple[str, str], tuple[str, str | None]]


def make_registry(
    entries: Entries | None = None,
    *,
    namespace: str = "https://spdx.org/spdxdocs/test-1",
    path: Path | None = None,
    project_root: Path | None = None,
) -> IdRegistry:
    """A registry holding *entries*, keyed the way the registry keys them
    (``_element_key``). With *path*, it is also saved there."""
    registry = IdRegistry(namespace=namespace, project_root=project_root)
    for (type_name, name), (spdx_id, sha256) in (entries or {}).items():
        key = _element_key(type_name=type_name, name=name)
        registry.elements[key] = RegistryEntry(spdx_id=spdx_id, sha256=sha256)
    if path is not None:
        registry.save(path)
    return registry


def entries_of(registry: IdRegistry) -> dict[tuple[str, str], tuple[str, str | None]]:
    """*registry*'s table as :func:`make_registry` takes it."""
    return {
        key: (entry.spdx_id, entry.sha256)
        for key, entry in sorted(registry.elements.items())
    }
