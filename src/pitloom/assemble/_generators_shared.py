# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Helpers shared by every SBOM generator.

See also:
- :mod:`pitloom.assemble._generators` for the project/sdist generator.
- :mod:`pitloom.assemble._generators_wheel` for the built-wheel generator.
- :mod:`pitloom.assemble._generators_env` for the installed-environment generator.
- :mod:`pitloom.assemble._model_generator` for AI model SBOM generation.
"""

from __future__ import annotations

from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3_bindings

from pitloom.export.hashes import sha256_of
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    IdRegistry,
    persist_registry,
    warn_no_registry_path,
)

# dataset_DatasetPackage is never harvested: a dataset id is pinned
# deliberately, by `loom id generate -e NAME:dataset_DatasetPackage` or
# `loom id import`, never from a run's fallback id. An ai_AIPackage is
# harvested only when hashed (see _harvestable).
_AUTO_HARVEST_EXCLUDED_TYPES = frozenset({DATASET_PACKAGE_TYPE})


def _harvestable(obj: Any) -> bool:
    """Return whether *obj* is safe for auto-harvest: not a dataset (see
    ``_AUTO_HARVEST_EXCLUDED_TYPES``), and an ``ai_AIPackage`` only when it
    carries a SHA-256. A hashed model's entry is content-gated, so its name
    cannot hand its id to other bytes; an unhashed model's name depends on
    which AI-format libraries extracted it."""
    get_compact_type = getattr(obj, "get_compact_type", None)
    compact_type = get_compact_type() if get_compact_type is not None else None
    if compact_type == AI_PACKAGE_TYPE:
        return sha256_of(obj) is not None
    return compact_type not in _AUTO_HARVEST_EXCLUDED_TYPES


def _sync_registry(
    exporter: Spdx3JsonExporter,
    registry: IdRegistry | None,
    update_id_registry: bool,
) -> None:
    """Harvest newly-minted ids from *exporter* back into *registry*.

    Elements that never looked the registry up
    (:attr:`~pitloom.export.spdx3_json.Spdx3JsonExporter.registry_non_readers`)
    are left out: neither written nor counted as a holder of their name,
    so the one element that does look a name up is written even when a
    non-reader shares its name.

    No-op when no registry was resolved or auto-update was disabled; a
    registry with no on-disk path to save to is not harvested into (the
    no-path ``WARNING:``). Saving and its log lines are
    :func:`~pitloom.id_registry.persist_registry`'s.
    """
    if registry is None or not update_id_registry:
        return
    if registry.path is None:
        warn_no_registry_path()
        return

    filtered = spdx3_bindings.SHACLObjectSet()
    non_readers = exporter.registry_non_readers
    for obj in exporter.object_set.objects:
        if _harvestable(obj) and getattr(obj, "spdxId", None) not in non_readers:
            filtered.add(obj)

    new_ids, changed = registry.harvest(filtered)
    persist_registry(registry, new_ids, changed)
