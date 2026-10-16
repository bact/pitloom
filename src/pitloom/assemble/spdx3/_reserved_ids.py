# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The registry-held ids a document's mints skip, shared by every document
builder (``loom project``/``wheel``/the hook/``embed-wheel``, ``loom env``,
``loom model``).

See also: :func:`pitloom.core.models.reserve_spdx_ids` (the reservation),
:class:`pitloom.id_registry.IdRegistrySession` (the claimed ids).
"""

from __future__ import annotations

from collections.abc import Iterable

from pitloom.core.ai_metadata import AiModelMetadata, cap_model_name
from pitloom.core.models import reserve_spdx_ids
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    PACKAGE_TYPE,
    IdRegistrySession,
)

__all__ = ["LOOKED_UP_TYPES", "model_dataset_keys", "reserve_held_ids"]

#: The types a document's elements look up: a miss mints in their prefix,
#: so every id the registry holds under one is reserved. Other types
#: (agents, tools) are minted the same way every run, their held ids
#: their own: reserving those would renumber them on the next run. A
#: dataset package is looked up by a loom fragment, not by the document.
LOOKED_UP_TYPES = frozenset(
    {AI_PACKAGE_TYPE, DATASET_PACKAGE_TYPE, FILE_TYPE, PACKAGE_TYPE}
)


def model_dataset_keys(
    models: Iterable[AiModelMetadata],
) -> tuple[tuple[str, str], ...]:
    """The (type, name) key of each dataset *models* bring in (a model
    card's): minted with no lookup, so the id ``id import`` held under it
    is its own, as for the deployed main package."""
    return tuple(
        (DATASET_PACKAGE_TYPE, cap_model_name(ref.metadata.name))
        for model in models
        for ref in model.datasets
    )


def _reserved_ids(
    session: IdRegistrySession, unlooked: tuple[tuple[str, str], ...]
) -> list[str]:
    """Every id *session* claimed, and every id its registry holds under a
    :data:`LOOKED_UP_TYPES` key, claimed or not, except those held under
    *unlooked*."""
    registry = session.registry
    if registry is None:
        return session.claimed_ids()
    own = {entry.spdx_id for key in unlooked if (entry := registry.get(*key))}
    held = [
        entry.spdx_id
        for key, entry in registry.elements.items()
        if key[0] in LOOKED_UP_TYPES and entry.spdx_id not in own
    ]
    return [*session.claimed_ids(), *held]


def reserve_held_ids(
    doc_name: str,
    doc_uuid: str,
    session: IdRegistrySession,
    *,
    unlooked: tuple[tuple[str, str], ...] = (),
) -> None:
    """Reserve in (*doc_name*, *doc_uuid*)
    (:func:`~pitloom.core.models.reserve_spdx_ids`) every id *session*
    claimed and every id its registry holds under a :data:`LOOKED_UP_TYPES`
    key, so a miss never mints the id another key holds. Not the ids held
    under *unlooked* (type, name) keys: elements minted with no lookup (the
    deployed main package, :func:`model_dataset_keys`), whose held id is
    their own. Call once per document, after its lookups and
    :func:`~pitloom.core.models._clear_doc_counters`, before its first
    mint."""
    reserve_spdx_ids(doc_name, doc_uuid, _reserved_ids(session, unlooked))
