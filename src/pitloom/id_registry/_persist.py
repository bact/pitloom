# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Save the ids a run added to a registry, beside other runs saving the
same file.

Every registry write goes through :func:`save_registry`: ``id generate``
and ``id import`` directly, every writer saving on a run's behalf
(project, wheel and env auto-harvest; loom at run exit) through
:func:`persist_registry`, so all log the same ``ID registry: ...`` lines.
It re-reads the file and re-applies only this object's own changes
(:func:`replay_changes`), then replaces the file atomically, so two runs
sharing one file keep both their entries and no counter goes down. There
is no lock: an update lost to a simultaneous save costs a re-mint on the
next run.

See also: :mod:`pitloom.id_registry._registry` (``IdRegistry.rebase``,
``IdRegistry.save``).
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, NamedTuple

from pitloom.core.quote_source import quote_source
from pitloom.id_registry._types import RegistryEntry

if TYPE_CHECKING:
    from pitloom.id_registry._registry import IdRegistry

log = logging.getLogger("pitloom.id_registry")

__all__ = [
    "Rebase",
    "added_ids",
    "new_id_count",
    "failed_to_save_message",
    "persist_registry",
    "replay_changes",
    "save_registry",
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
        added: Distinct ids a save adds to the file that the table this
            object last read did not hold either (:func:`new_id_count`).
    """

    refused: int
    pending: bool
    added: int


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


def new_id_count(table: Table, *held: Table) -> int:
    """The number of distinct ids *table* holds that no table of *held*
    does, under any key."""
    known = {entry.spdx_id for other in held for entry in other.values()}
    return len({entry.spdx_id for entry in table.values()} - known)


def replay_changes(base: Table, mine: Table, theirs: Table) -> tuple[Table, int]:
    """*theirs* with the changes *mine* made to *base* applied again.

    A changed key is one whose entry differs between *base* and *mine*: it
    takes *mine*'s entry, or is dropped when *mine* dropped it. Every other
    key keeps *theirs*'. A known id *mine* moved to another key (a
    promotion: the old key dropped, the new one added) is replayed as such.
    A changed entry whose id *theirs* holds under a key that keeps
    *theirs*' entry, and which *mine* does not map to that id too, is
    refused with one ``WARNING:``: another run saved that id first --
    minted from the same table, or a known id moved to another key -- and
    two keys never share an id. A refused key keeps *theirs*' entry, whose
    id may refuse another changed entry in turn, so refusal is repeated
    until no new key is refused.

    Returns the table and the number of distinct ids not replayed.
    """
    changed = sorted(
        key for key in base.keys() | mine.keys() if base.get(key) != mine.get(key)
    )
    untouched = theirs.keys() - set(changed)
    refused: dict[tuple[str, str], tuple[str, str]] = {}
    while True:
        kept = sorted(untouched | (refused.keys() & theirs.keys()))
        held = {theirs[key].spdx_id: key for key in kept}
        merged, now = _replay(changed, mine, theirs, held)
        if now.keys() <= refused.keys():
            break
        refused.update(now)
    for key, holder in now.items():
        log.warning(
            "ID registry: another run saved %s for %s %r first; "
            "not recording it for %r",
            _id_of(mine.get(key)),
            holder[0],
            holder[1],
            key[1],
        )
    return merged, len({_id_of(mine.get(key)) for key in now})


def _replay(
    changed: list[tuple[str, str]],
    mine: Table,
    theirs: Table,
    held: dict[str, tuple[str, str]],
) -> tuple[Table, dict[tuple[str, str], tuple[str, str]]]:
    """One replay pass: *theirs* with each *changed* key's entry from
    *mine*, except one whose id another key of *held* (id -> key) holds.
    Returns the table and the refused keys, each with that holder."""
    merged = dict(theirs)
    refused: dict[tuple[str, str], tuple[str, str]] = {}
    for key in changed:
        entry = mine.get(key)
        if entry is None:
            merged.pop(key, None)
            continue
        holder = held.get(entry.spdx_id)
        if holder is not None and _id_of(mine.get(holder)) != entry.spdx_id:
            refused[key] = holder
        else:
            merged[key] = entry
    return merged, refused


def _id_of(entry: RegistryEntry | None) -> str | None:
    return entry.spdx_id if entry is not None else None


def failed_to_save_message(
    path: str | os.PathLike[str] | None, exc: BaseException
) -> str:
    """The one line for a registry save that failed: ``ID registry: failed
    to save <path>: <reason>``. A ``WARNING:`` where the run's output is
    already written (:func:`persist_registry`), an ``ERROR:`` for ``id
    generate``/``id import``, whose output is the registry."""
    return f"ID registry: failed to save {path}: {exc}"


def warn_no_registry_path() -> None:
    """Log the one ``WARNING:`` for a registry with no file to save to."""
    log.warning("ID registry: no file path resolved; skipping auto-update.")


def save_registry(registry: IdRegistry) -> Rebase:
    """Re-read *registry*'s file, apply this object's changes again
    (:meth:`~pitloom.id_registry.IdRegistry.rebase`) and save the result
    when it differs from the file; a new file is saved as it is.

    Raises:
        OSError, ValueError: the re-read or the write failed; the file is
            left as it was.
    """
    rebased = registry.rebase()
    if rebased.pending:
        registry.save()
    return rebased


def persist_registry(registry: IdRegistry, new_ids: int, changed: bool) -> None:
    """Save what a run added to *registry* and log the outcome.

    *new_ids* counts the distinct ids the run added; *changed* says whether
    it changed anything at all. With no file path: the no-path ``WARNING:``.
    Nothing changed: nothing. Else :func:`save_registry`, and one ``INFO:``
    when it wrote, counting the new ids the save adds to the file, at most
    *new_ids* (so neither another run's ids nor a refused one count). A
    failure, the re-read included, is one ``WARNING:`` and otherwise
    ignored: the run's own output is already written.
    """
    if registry.path is None:
        warn_no_registry_path()
        return
    if not changed:
        return
    try:
        rebased = save_registry(registry)
    except (OSError, ValueError) as exc:
        log.warning("%s", failed_to_save_message(registry.path, exc))
        return
    if not rebased.pending:
        return
    added = min(new_ids, rebased.added)
    if added:
        log.info(
            "ID registry: added %d new id(s) to %s", added, quote_source(registry.path)
        )
    else:
        # Changed, but no new id: a stale key was released in the same pass
        # another claimed its id, an id was promoted to its lookup key (see
        # pitloom.id_registry._harvest._release_stale_keys_for_id), or an
        # entry's hash changed.
        log.info(
            "ID registry: updated stale entries in %s", quote_source(registry.path)
        )
