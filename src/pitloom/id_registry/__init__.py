# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Loom ID registry: stable SPDX IDs keyed by ``(compact type, name)``; a
``software_Package``'s name holds its version (``package_key``).

See also: :mod:`pitloom.id_registry._types` for ``RegistryEntry``, the
type constants and file traversal, :mod:`pitloom.id_registry._registry`
for ``IdRegistry`` itself, :mod:`pitloom.id_registry._format` for the
file format, :mod:`pitloom.id_registry._counters` for the id counters,
:mod:`pitloom.id_registry._generate` for indexing a project's files,
:mod:`pitloom.id_registry._harvest` for SBOM-element harvest
helpers, :mod:`pitloom.id_registry._ambiguous` for the keys harvest does
not write, :mod:`pitloom.id_registry._session` for ``IdRegistrySession``,
:mod:`pitloom.id_registry._persist` for saving a run's additions,
:mod:`pitloom.id_registry._sbom_read` for reading an SBOM for ``id import``,
:mod:`pitloom.id_registry.import_keys` for the keys ``id import`` writes,
:mod:`pitloom.id_registry.resolve` for registry resolution,
:mod:`pitloom.id_registry.keys` for registry keys.

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
from pitloom.id_registry._session import (
    IdRegistrySession,
    info_identity_unknown,
    warn_claim_collision,
)
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
from pitloom.id_registry.keys import (
    Alias,
    LookupKey,
    alias_candidates,
    alias_tail,
    artifact_key,
    is_layout_alias,
    join_key,
    package_key,
    package_version_key,
    path_key,
    project_prefix,
    split_package_key,
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
    "Alias",
    "DATASET_PACKAGE_TYPE",
    "DEFAULT_ID_REGISTRY_FILENAME",
    "FILE_TYPE",
    "IdRegistry",
    "IdRegistrySession",
    "LookupKey",
    "PACKAGE_TYPE",
    "RegistryEntry",
    "alias_candidates",
    "alias_tail",
    "ambiguous_keys_message",
    "artifact_key",
    "failed_to_save_message",
    "info_identity_unknown",
    "is_layout_alias",
    "join_key",
    "package_key",
    "package_version_key",
    "path_key",
    "persist_registry",
    "project_prefix",
    "registry_base_dir",
    "registry_copy",
    "registry_file_path",
    "registry_key_for_path",
    "resolve_registry",
    "save_registry",
    "sha256_file",
    "split_package_key",
    "type_id_prefix",
    "warn_claim_collision",
    "warn_no_registry_path",
]
