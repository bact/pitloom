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

import logging
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3_bindings

from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.id_registry import IdRegistry

log = logging.getLogger(__name__)

# ai_AIPackage is deliberately excluded from auto-harvest: its correct
# registry key is the model file's stem (only ever registered via the
# extras-free `loom id generate`), not its `.name`, which is
# extraction-dependent and varies with whether AI-format libraries are
# installed. Harvesting it by name would write entries that never match
# future lookups (see `_lookup_ai_model_entity`,
# pitloom.assemble.spdx3._ai_package) instead of just doing nothing.
#
# dataset_DatasetPackage is excluded for a related but simpler reason:
# `_build_dataset_package` (pitloom.assemble.spdx3.dataset) never consults
# the registry at all -- every dataset spdxId is freshly minted every run,
# with no lookup path to match a harvested entry against. Harvesting it
# would just write a dead, silently-overwritten entry every run.
_AUTO_HARVEST_EXCLUDED_TYPES = frozenset({"ai_AIPackage", "dataset_DatasetPackage"})


def _harvestable(obj: Any) -> bool:
    """Return whether *obj* is safe for auto-harvest (see the comment above
    ``_AUTO_HARVEST_EXCLUDED_TYPES``)."""
    get_compact_type = getattr(obj, "get_compact_type", None)
    compact_type = get_compact_type() if get_compact_type is not None else None
    return compact_type not in _AUTO_HARVEST_EXCLUDED_TYPES


def _sync_registry(
    exporter: Spdx3JsonExporter,
    registry: IdRegistry | None,
    update_id_registry: bool,
) -> None:
    """Harvest newly-minted ids from *exporter* back into *registry*.

    No-op when no registry was resolved, auto-update was disabled, or the
    registry has no on-disk path to save to. A save failure is logged as a
    ``WARNING`` and otherwise ignored -- it must never break SBOM
    generation itself.
    """
    if registry is None or not update_id_registry:
        return
    if registry.path is None:
        log.warning("ID registry: no file path resolved; skipping auto-update.")
        return

    filtered = spdx3_bindings.SHACLObjectSet()
    for obj in exporter.object_set.objects:
        if _harvestable(obj):
            filtered.add(obj)

    new_files, new_entities, changed = registry.harvest(filtered)
    if not changed:
        return
    try:
        registry.save()
    except OSError as exc:
        log.warning("ID registry: failed to save %s: %s", registry.path, exc)
        return
    if new_files or new_entities:
        log.info(
            "ID registry: added %d new file(s), %d new entit(y/ies) to %s",
            new_files,
            new_entities,
            registry.path,
        )
    else:
        # changed is True but the net counts are zero: a stale key was
        # released in the same pass a new one claimed its id (see
        # pitloom.id_registry._harvest._release_stale_keys_for_id) -- real content
        # changed even though nothing was added or removed net.
        log.info("ID registry: updated stale entries in %s", registry.path)
