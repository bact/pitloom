# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Loom ID registry: a stable file/entity -> SPDX ID registry.

See also: :mod:`pitloom.id_registry._types` for registry dataclasses and
file traversal, :mod:`pitloom.id_registry._registry` for ``IdRegistry``
itself, :mod:`pitloom.id_registry._harvest` for SBOM-element harvest
helpers, :mod:`pitloom.id_registry._session` for ``IdRegistrySession``,
:mod:`pitloom.id_registry.resolve` for registry resolution.

Underscore-prefixed names (e.g. ``_entity_key``, ``_import_sbom_element``)
are internal and not re-exported here -- import them from the submodule
that defines them.
"""

from __future__ import annotations

from pitloom.id_registry._registry import IdRegistry
from pitloom.id_registry._session import IdRegistrySession, warn_claim_collision
from pitloom.id_registry._types import (
    DEFAULT_ID_REGISTRY_FILENAME,
    DIRECTORY_ENTITY_TYPE,
    PACKAGE_ENTITY_TYPE,
    EntityEntry,
    FileEntry,
    sha256_file,
)
from pitloom.id_registry.resolve import registry_base_dir, resolve_registry

__all__ = [
    "DEFAULT_ID_REGISTRY_FILENAME",
    "DIRECTORY_ENTITY_TYPE",
    "PACKAGE_ENTITY_TYPE",
    "EntityEntry",
    "FileEntry",
    "IdRegistry",
    "IdRegistrySession",
    "registry_base_dir",
    "resolve_registry",
    "sha256_file",
    "warn_claim_collision",
]
