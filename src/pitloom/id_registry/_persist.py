# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Save the ids a run added to a registry, beside other runs saving the
same file.

Every writer that saves on a run's behalf (project, wheel and env
auto-harvest; loom at run exit) goes through :func:`persist_registry`, so
all log the same ``ID registry: ...`` lines. It re-reads the file and
re-applies only this run's own changes (:func:`replay_changes`), then
replaces the file atomically, so two runs sharing one file keep both their
entries. There is no lock: an update lost to a simultaneous save costs a
re-mint on the next run.

See also: :mod:`pitloom.id_registry._registry` (``IdRegistry.rebase``,
``IdRegistry.save``).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

from pitloom.id_registry._types import RegistryEntry

if TYPE_CHECKING:
    from pitloom.id_registry._registry import IdRegistry

log = logging.getLogger("pitloom.id_registry")

__all__ = [
    "Rebase",
    "added_ids",
    "persist_registry",
    "replay_changes",
    "warn_no_registry_path",
]

#: A registry table, keyed by ``(compact type, name)``.
Table = dict[tuple[str, str], RegistryEntry]


class Rebase(NamedTuple):
    """What :meth:`~pitloom.id_registry.IdRegistry.rebase` did.

    Attributes:
        refused: Distinct new ids not replayed: another run saved each one
            first, for another key.
        pending: The registry still differs from its file.
    """

    refused: int
    pending: bool


def added_ids(before: Table, after: Table) -> int:
    """The number of distinct ids *after* holds that *before* did not, each
    only under keys *before* did not hold: an id that replaced a key's
    entry is an update, not an addition."""
    held = {entry.spdx_id for entry in before.values()}
    new: dict[str, bool] = {}
    for key, entry in after.items():
        if entry.spdx_id not in held:
            new[entry.spdx_id] = new.get(entry.spdx_id, True) and key not in before
    return sum(new.values())


def replay_changes(base: Table, mine: Table, theirs: Table) -> tuple[Table, int]:
    """*theirs* with the changes *mine* made to *base* applied again.

    A changed key is one whose entry differs between *base* and *mine*: it
    takes *mine*'s entry, or is dropped when *mine* dropped it. Every other
    key keeps *theirs*'. A changed entry whose id *theirs* holds under a key
    *mine* did not change, and which *mine* does not map to that id too (a
    src-layout alias), is not replayed and gets one ``WARNING:``: another
    run saved that id first -- minted from the same table, or a known id
    moved to another key -- and two keys never share an id.

    Returns the table and the number of distinct ids not replayed.
    """
    changed = sorted(
        key for key in base.keys() | mine.keys() if base.get(key) != mine.get(key)
    )
    untouched = theirs.keys() - set(changed)
    held = {theirs[key].spdx_id: key for key in sorted(untouched)}
    merged = dict(theirs)
    refused: set[str] = set()
    for key in changed:
        entry = mine.get(key)
        holder = held.get(entry.spdx_id) if entry is not None else None
        if entry is None:
            merged.pop(key, None)
        elif holder is not None and _id_of(mine.get(holder)) != entry.spdx_id:
            log.warning(
                "ID registry: another run saved %s for %s %r first; "
                "not recording it for %r",
                entry.spdx_id,
                holder[0],
                holder[1],
                key[1],
            )
            refused.add(entry.spdx_id)
        else:
            merged[key] = entry
    return merged, len(refused)


def _id_of(entry: RegistryEntry | None) -> str | None:
    return entry.spdx_id if entry is not None else None


def warn_no_registry_path() -> None:
    """Log the one ``WARNING:`` for a registry with no file to save to."""
    log.warning("ID registry: no file path resolved; skipping auto-update.")


def persist_registry(registry: IdRegistry, new_ids: int, changed: bool) -> None:
    """Save what a run added to *registry* and log the outcome.

    *new_ids* counts the distinct ids the run added; *changed* says whether
    it changed anything at all. With no file path: the no-path ``WARNING:``.
    Nothing changed: nothing. Else the file is re-read and the run's
    changes re-applied (:meth:`~pitloom.id_registry.IdRegistry.rebase`),
    the result saved atomically, and one ``INFO:`` logged. A failure, the
    re-read included, is one ``WARNING:`` and otherwise ignored: the run's
    own output is already written.
    """
    if registry.path is None:
        warn_no_registry_path()
        return
    if not changed:
        return
    try:
        rebased = registry.rebase()
        if not rebased.pending:
            return
        registry.save()
    except (OSError, ValueError) as exc:
        log.warning("ID registry: failed to save %s: %s", registry.path, exc)
        return
    if new_ids > rebased.refused:
        log.info(
            "ID registry: added %d new id(s) to %s",
            new_ids - rebased.refused,
            registry.path,
        )
    else:
        # Changed, but no new id: a stale key was released in the same pass
        # another claimed its id (see
        # pitloom.id_registry._harvest._release_stale_keys_for_id), or an
        # entry's hash changed.
        log.info("ID registry: updated stale entries in %s", registry.path)
