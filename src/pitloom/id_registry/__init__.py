# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Loom ID registry: stable SPDX IDs keyed by ``(compact type, name)``.

See also: :mod:`pitloom.id_registry._types` for ``RegistryEntry``, the
type constants and file traversal, :mod:`pitloom.id_registry._registry`
for ``IdRegistry`` itself, :mod:`pitloom.id_registry._format` for the
file format, :mod:`pitloom.id_registry._harvest` for SBOM-element harvest
helpers, :mod:`pitloom.id_registry._ambiguous` for the keys harvest does
not write, :mod:`pitloom.id_registry._session` for ``IdRegistrySession``,
:mod:`pitloom.id_registry._persist` for saving a run's additions,
:mod:`pitloom.id_registry.resolve` for registry resolution.

Underscore-prefixed names (e.g. ``_element_key``, ``_import_sbom_element``)
are internal and not re-exported here -- import them from the submodule
that defines them.
"""

from __future__ import annotations

from pitloom.id_registry._ambiguous import ambiguous_keys_message
from pitloom.id_registry._persist import (
    failed_to_save_message,
    persist_registry,
    save_registry,
    warn_no_registry_path,
)
from pitloom.id_registry._registry import IdRegistry
from pitloom.id_registry._session import IdRegistrySession, warn_claim_collision
from pitloom.id_registry._types import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    DEFAULT_ID_REGISTRY_FILENAME,
    FILE_TYPE,
    PACKAGE_TYPE,
    RegistryEntry,
    sha256_file,
    type_id_prefix,
)
from pitloom.id_registry.resolve import (
    registry_base_dir,
    registry_copy,
    registry_file_path,
    registry_key_for_path,
    resolve_registry,
)

__all__ = [
    "AI_PACKAGE_TYPE",
    "DATASET_PACKAGE_TYPE",
    "DEFAULT_ID_REGISTRY_FILENAME",
    "FILE_TYPE",
    "IdRegistry",
    "IdRegistrySession",
    "PACKAGE_TYPE",
    "RegistryEntry",
    "ambiguous_keys_message",
    "failed_to_save_message",
    "persist_registry",
    "registry_base_dir",
    "registry_copy",
    "registry_file_path",
    "registry_key_for_path",
    "resolve_registry",
    "save_registry",
    "sha256_file",
    "type_id_prefix",
    "warn_claim_collision",
    "warn_no_registry_path",
]
