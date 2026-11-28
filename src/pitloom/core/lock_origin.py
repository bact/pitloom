# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which lock/pin source gave a project's locked dependencies, as typed
facts, and the two texts made from them: the provenance string and the
seed text of the document id.

See also: :mod:`pitloom.extract.lock.cascade` (which source wins),
:func:`pitloom.core.models.compute_doc_uuid` (what the seed text feeds).
"""

from __future__ import annotations

from typing import NamedTuple

from pitloom.core.provenance import provenance_segment, provenance_source

__all__ = ["LockOrigin", "lock_provenance", "lock_seed_text"]


class LockOrigin(NamedTuple):
    """The lock/pin source of a project's locked dependencies.

    Attributes:
        source: The source's name in the lock cascade (``"uv.lock"``).
        method: How it was read (``"resolved_lockfile"``,
            ``"pinned_requirements"``).
        supersedes: The lower-priority source whose result this one
            replaced, ``None`` when there was none.
    """

    source: str
    method: str
    supersedes: str | None = None


def lock_provenance(origin: LockOrigin) -> str:
    """The ``provenance["locked_dependencies"]`` string of *origin*."""
    provenance = provenance_segment(
        provenance_source(origin.source), "Method", origin.method
    )
    if origin.supersedes is not None:
        provenance = provenance_segment(
            provenance, "Note", f"supersedes {origin.supersedes}"
        )
    return provenance


def lock_seed_text(origin: LockOrigin) -> str:
    """The text *origin* adds to the seed of the document id.

    Frozen: an id input, so a change here changes every SPDX id of a
    document with a lock. It is written out here and shares nothing with
    :func:`lock_provenance`, whose labels may be reworded freely.

    Target (taxonomy code stage): this function is the only lock input of
    the seed; today a ``ProjectMetadata`` without a ``LockOrigin`` still
    seeds from its provenance string (see
    :meth:`pitloom.core.project.ProjectMetadata.locked_dependencies_seed`).
    """
    text = f"Source: {origin.source} | Method: {origin.method}"
    if origin.supersedes is not None:
        text += f" | Note: supersedes {origin.supersedes}"
    return text
