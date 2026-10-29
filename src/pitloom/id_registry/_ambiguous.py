# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The key harvest writes an element under, and the keys it cannot pin.

See also: :mod:`pitloom.id_registry._harvest` (its
``_import_sbom_element`` writes the keys this module predicts).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from typing import Any, NamedTuple

from pitloom.export.hashes import sha256_of
from pitloom.id_registry._types import FILE_TYPE, _element_key

__all__ = [
    "MODEL_NOT_RECORDED_INFO",
    "NO_UNIQUE_FILE",
    "DerivedKeys",
    "KeptPairs",
    "RecordedHashes",
    "RecordedKeys",
    "WrittenKey",
    "_ambiguous_keys",
    "_compact_type_of",
    "_element_key_of",
    "_written_key",
    "ambiguous_keys_message",
    "harvest_sha256",
    "unique_file_keys",
]

#: Why a hashed model is not keyed by its file: no file, or several, hold
#: its SHA-256. Shared by every model ``INFO:`` that says so.
NO_UNIQUE_FILE = "no unique file with its SHA-256"
#: ``log.info()`` format for a hashed model a run's auto-harvest leaves out
#: (no recorded key, no :func:`unique_file_keys` file). Argument: its name.
MODEL_NOT_RECORDED_INFO = f"ID registry: model %s not recorded: {NO_UNIQUE_FILE}"

#: spdxId -> (compact type, raw key) a run's lookups recorded for it
#: (:meth:`~pitloom.id_registry.IdRegistrySession.recorded_keys`).
RecordedKeys = Mapping[str, tuple[str, str]]
#: spdxId -> the SHA-256 a run's harvest records for a file in place of the
#: one its element states: a Git LFS pointer's ``oid``
#: (:meth:`~pitloom.id_registry.IdRegistrySession.recorded_hashes`).
RecordedHashes = Mapping[str, str]
#: (spdxId, written key) pairs of elements harvest never writes (R-keep).
KeptPairs = AbstractSet[tuple[str, tuple[str, str]]]


class DerivedKeys(dict[str, tuple[str, str]]):
    """spdxId -> (compact type, raw key) derived, not recorded by a run's
    lookup (``id import``'s
    :func:`~pitloom.id_registry.import_keys.import_keys`, a run's
    fragment model): written like a recorded key, but R-keep and the stale
    rule apply as to a name. The ids in :attr:`recorded` are the run's
    recorded keys."""

    def __init__(
        self,
        items: Mapping[str, tuple[str, str]] | None = None,
        *,
        recorded: Iterable[str] = (),
    ) -> None:
        super().__init__(items or {})
        #: The spdxIds whose key a run's lookup recorded.
        self.recorded = frozenset(recorded)


class WrittenKey(NamedTuple):
    """The registry *key* an element is written under, and whether it is
    the run's *recorded* key (else the element's type and name, or a key
    ``id import`` derived)."""

    key: tuple[str, str]
    recorded: bool


def _compact_type_of(obj: Any) -> str:
    """The SPDX 3 compact type name of *obj* (its class name as fallback)."""
    get_compact_type = getattr(obj, "get_compact_type", None)
    compact_type = get_compact_type() if get_compact_type is not None else None
    return compact_type or type(obj).__name__


def _element_key_of(obj: Any) -> tuple[str, str] | None:
    """*obj*'s own key, its type and name, or ``None`` when it has none
    (unnamed, no id, or no SPDX 3 compact type)."""
    name = getattr(obj, "name", None)
    if not name or not getattr(obj, "spdxId", None):
        return None
    compact_type = _compact_type_of(obj)
    if compact_type == "object":
        return None
    return _element_key(type_name=compact_type, name=name)


def _written_key(obj: Any, keys: RecordedKeys | None) -> WrittenKey | None:
    """The key :func:`~pitloom.id_registry._harvest._import_sbom_element`
    writes *obj* under: the key *keys* holds for its spdxId when that is of
    *obj*'s own type and not empty (``recorded`` unless *keys* are
    :class:`DerivedKeys`); else :func:`_element_key_of`. ``None`` when *obj*
    has no key of its own."""
    own = _element_key_of(obj)
    if own is None or not keys:
        return None if own is None else WrittenKey(own, recorded=False)
    recorded = keys.get(str(obj.spdxId))
    if recorded is None or recorded[0] != own[0] or not recorded[1]:
        return WrittenKey(own, recorded=False)
    derived = isinstance(keys, DerivedKeys) and str(obj.spdxId) not in keys.recorded
    return WrittenKey(
        _element_key(type_name=own[0], name=recorded[1]), recorded=not derived
    )


def harvest_sha256(obj: Any, hashes: RecordedHashes | None) -> str | None:
    """The SHA-256 harvest reads for *obj*: a ``software_File``'s entry in
    *hashes* (its run recorded one: a Git LFS pointer's ``oid``), else the
    one *obj* states (:func:`~pitloom.export.hashes.sha256_of`). Every
    harvest reader of an element's hash goes through here, so they agree."""
    if hashes and _compact_type_of(obj) == FILE_TYPE:
        recorded = hashes.get(str(getattr(obj, "spdxId", None)))
        if recorded is not None:
            return recorded
    return sha256_of(obj)


def unique_file_keys(
    objects: Iterable[Any],
    keys: RecordedKeys | None,
    hashes: RecordedHashes | None = None,
) -> dict[str, str]:
    """SHA-256 (:func:`harvest_sha256`, with *hashes*) -> the
    :func:`_written_key` (with *keys*) of the one ``software_File`` of
    *objects* holding it, for each SHA-256 exactly one file holds: the key
    a model of those bytes is written under."""
    files = [
        (sha, _written_key(obj, keys))
        for obj in objects
        if _compact_type_of(obj) == FILE_TYPE
        and (sha := harvest_sha256(obj, hashes)) is not None
    ]
    counts = Counter(sha for sha, _ in files)
    return {
        sha: key.key[1] for sha, key in files if counts[sha] == 1 and key is not None
    }


def _ambiguous_keys(
    objects: Iterable[Any],
    keys: RecordedKeys | None = None,
    *,
    kept: KeptPairs = frozenset(),
) -> frozenset[tuple[str, str]]:
    """Every key more than one of *objects* would be written under
    (:func:`_written_key`, with *keys*), file paths included. An element
    whose (spdxId, written key) is in *kept* is never written (R-keep), so
    it neither counts nor blocks another.

    One document holding two elements of one type and one written key --
    two pinned versions of one dependency, two bundled binaries of one
    name, two wheel members normalised to one path -- cannot be pinned by
    the registry: writing either id would make the next run hand it to
    whichever element claims the key first, which is not the one
    harvested. Two elements of one name but distinct recorded keys are
    not ambiguous.

    A run's auto-harvest
    (:func:`pitloom.assemble._generators_shared._sync_registry`) first
    leaves out the elements that never look the registry up (a non-PEP 508
    dependency string named like the project, a phantom named like the
    project or a dependency), so they neither count nor get written, and
    the one element that looks the name up is written. ``id import`` has
    no such record and passes every element.
    """
    counts: Counter[tuple[str, str]] = Counter()
    for obj in objects:
        found = _written_key(obj, keys)
        if found is not None and (str(obj.spdxId), found.key) not in kept:
            counts[found.key] += 1
    return frozenset(key for key, count in counts.items() if count > 1)


def ambiguous_keys_message(outcome: str, keys: Iterable[tuple[str, str]]) -> str:
    """The one line naming the :func:`_ambiguous_keys` *keys* left out:
    ``ID registry: <outcome> (name held by several elements): <type>
    '<name>', ...``, sorted, each name ``repr()``'d so a control character
    in it cannot forge the line. Shared by ``id import``'s ``INFO:`` and
    run auto-harvest's DEBUG record."""
    listed = ", ".join(f"{type_name} {name!r}" for type_name, name in sorted(keys))
    return f"ID registry: {outcome} (name held by several elements): {listed}"
