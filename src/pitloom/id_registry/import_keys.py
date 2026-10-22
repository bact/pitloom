# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The keys ``id import`` writes a file, a dataset package and a model
under, and the dataset name-key wording loom shares.

A run looks a file up by its path key (a layout alias included), a dataset
package by its path key and a model by its own file's key; an imported
SBOM records none of them, so ``id import`` derives them here. See also:
:mod:`pitloom.id_registry._harvest` (writes them),
:mod:`pitloom.id_registry.keys` (path keys), :mod:`pitloom._loom_dataset`
(the loom lookup of a dataset package).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, NamedTuple

from pitloom.export.hashes import sha256_of
from pitloom.id_registry._ambiguous import (
    NO_UNIQUE_FILE,
    DerivedKeys,
    _element_key_of,
    unique_file_keys,
)
from pitloom.id_registry._types import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    _element_key,
)
from pitloom.id_registry.keys import (
    LAYOUT_ALIAS_HITS_INFO,
    alias_candidates,
    artifact_key,
)
from pitloom.logging_config import loggable

if TYPE_CHECKING:
    from pitloom.id_registry._registry import IdRegistry

log = logging.getLogger("pitloom.id_registry")

__all__ = [
    "DATASET_NAME_KEY_INFO",
    "DATASET_PATH_KEY_INFO",
    "DATASET_PIN_GATED_INFO",
    "FILE_ALIAS_OVER_CHANGED_INFO",
    "IMPORT_NOT_FOUND",
    "LAYOUT_ALIAS_CHANGED_INFO",
    "MODEL_FILE_ENTRY_KEY_INFO",
    "MODEL_NAME_KEY_INFO",
    "ImportPlan",
    "import_keys",
    "name_key_reason",
    "report_imported",
]

#: ``log.info()`` formats, once per element: a dataset package keyed by its
#: name (loom per package per run, ``id import`` per package; arguments:
#: the name, :func:`name_key_reason` or :data:`IMPORT_NOT_FOUND`), a dataset
#: ``id import`` keys by a path spelt otherwise than its name (the name, the
#: key), an imported model left under its name (the name) and one keyed by
#: the registry's file entry of its SHA-256 (the name, the key).
DATASET_NAME_KEY_INFO = "ID registry: dataset %s keyed by its name: %s"
DATASET_PATH_KEY_INFO = "ID registry: dataset %s keyed by its path: %s"
MODEL_NAME_KEY_INFO = f"ID registry: model %s imported under its name: {NO_UNIQUE_FILE}"
MODEL_FILE_ENTRY_KEY_INFO = (
    "ID registry: model %s keyed by the registry's file with its SHA-256: %s"
)
#: ``log.info()`` formats, once per run, for a key held with other content
#: whose layout alias holds the new content: as a run's lookup hits the
#: alias, the file keeps one id. ``id generate`` moved the alias's entry
#: over the key; ``id import`` wrote the file under the alias. Argument:
#: the count.
LAYOUT_ALIAS_CHANGED_INFO = (
    "ID registry: %d key(s) of changed content took their layout alias's id"
)
FILE_ALIAS_OVER_CHANGED_INFO = (
    "ID registry: %d file(s) imported under their layout alias: "
    "their own key holds other content"
)
#: ``log.info()`` format for a dataset package pin with no SHA-256 that
#: ``id generate -e`` gives one: it keeps its id. Argument: the key.
DATASET_PIN_GATED_INFO = "ID registry: dataset %s pin now gated by its SHA-256"
#: The ``id import`` reason for a dataset name found neither below the root
#: nor from the current directory: a loom script declared it relative to
#: its own directory.
IMPORT_NOT_FOUND = (
    "not found: declare paths relative to the registry root "
    "or run id import from the directory the script ran in"
)


class _Note(NamedTuple):
    """An ``INFO:`` due once the element *spdx_id* is written under *key*."""

    spdx_id: str
    key: tuple[str, str]
    message: str
    args: tuple[str, ...]


class ImportPlan(NamedTuple):
    """What :func:`import_keys` derived: the *keys* to write elements under,
    the *notes* (``INFO:`` lines) due for those actually written, and the
    files keyed by a held layout alias (*aliased*: spdxId and key;
    *over_changed*: the spdxIds of those whose own key holds other
    content)."""

    keys: DerivedKeys
    notes: tuple[_Note, ...] = ()
    aliased: tuple[tuple[str, tuple[str, str]], ...] = ()
    over_changed: frozenset[str] = frozenset()


def name_key_reason(path: str | os.PathLike[str]) -> str:
    """Why an artifact at *path* is keyed by its name: ``not found`` or
    ``outside the project root``."""
    return "outside the project root" if os.path.lexists(path) else "not found"


def _directory(get: Callable[[], str | os.PathLike[str]]) -> str | None:
    """The directory *get* returns, or ``None`` on ``OSError`` (no project
    root, and the current directory was deleted)."""
    try:
        return os.fspath(get())
    except OSError:
        return None


def _file_alias(
    registry: IdRegistry, name: str, sha: str | None
) -> tuple[str, bool] | None:
    """The one held layout alias of the imported file *name* recording its
    *sha* (:func:`~pitloom.id_registry.keys.alias_candidates`), when *name*
    itself is not held with *sha*: the key a run looks the file up
    through. With it, whether *name* is held (with other content), which
    would otherwise give one file two ids."""
    if sha is None:
        return None
    own = registry.get(FILE_TYPE, name)
    if own is not None and own.sha256 == sha.lower():
        return None
    found = alias_candidates(registry, FILE_TYPE, name, sha)
    return (found[0], own is not None) if len(found) == 1 else None


def _dataset_key(
    registry: IdRegistry, name: str, file_key: str | None
) -> tuple[str, tuple[str, tuple[str, ...]] | None]:
    """The key of the imported dataset package *name* and its ``INFO:``
    (format, arguments), if any: the path key of the first that names a
    file or directory below the root of: its one same-hash file's key
    (*file_key*, from the root), *name* from the root, *name* from the
    current directory; else *name*."""
    root, cwd = _directory(registry.root_dir), _directory(os.getcwd)
    texts = [name] if file_key is None else [file_key, name]
    paths = [os.path.join(root, text) for text in texts] if root is not None else []
    paths += [os.path.join(cwd, name)] if cwd is not None else []
    for path in paths:
        found = artifact_key(registry, path=path, name=name)
        if found.path:
            if found.key == name:
                return name, None
            return found.key, (
                DATASET_PATH_KEY_INFO,
                (loggable(name), loggable(found.key)),
            )
    outside = any(os.path.lexists(path) for path in paths)
    reason = name_key_reason(paths[0]) if outside else IMPORT_NOT_FOUND
    return name, (DATASET_NAME_KEY_INFO, (loggable(name), reason))


def _held_files(registry: IdRegistry) -> dict[str, list[str]]:
    """SHA-256 -> the held ``software_File`` keys recording it."""
    held: dict[str, list[str]] = {}
    for (type_name, name), entry in sorted(registry.elements.items()):
        if type_name == FILE_TYPE and entry.sha256 is not None:
            held.setdefault(entry.sha256, []).append(name)
    return held


class _Planner:
    """The state :func:`import_keys` builds one :class:`ImportPlan` with."""

    def __init__(self, registry: IdRegistry, objects: list[Any]) -> None:
        self.registry = registry
        self.keys = DerivedKeys()
        self.notes: list[_Note] = []
        self.aliased: list[tuple[str, tuple[str, str]]] = []
        self.over_changed: set[str] = set()
        for obj in objects:
            own = _element_key_of(obj)
            if own is not None and own[0] == FILE_TYPE:
                alias = _file_alias(registry, own[1], sha256_of(obj))
                if alias is not None:
                    spdx_id = str(obj.spdxId)
                    self.aliased.append((spdx_id, self.key(obj, FILE_TYPE, alias[0])))
                    if alias[1]:
                        self.over_changed.add(spdx_id)
        self.files = unique_file_keys(objects, self.keys)
        self.held = _held_files(registry)

    def key(self, obj: Any, type_name: str, key: str) -> tuple[str, str]:
        """Derive *key* for *obj*; its registry key."""
        self.keys[str(obj.spdxId)] = (type_name, key)
        return _element_key(type_name=type_name, name=key)

    def note(
        self, obj: Any, key: tuple[str, str], said: tuple[str, tuple[str, ...]]
    ) -> None:
        self.notes.append(_Note(str(obj.spdxId), key, said[0], said[1]))

    def dataset(self, obj: Any, name: str) -> None:
        sha = sha256_of(obj)
        key, said = _dataset_key(self.registry, name, self.files.get(sha or ""))
        written = self.key(obj, DATASET_PACKAGE_TYPE, key)
        if said is not None:
            self.note(obj, written, said)

    def model(self, obj: Any, own: tuple[str, str]) -> None:
        sha = sha256_of(obj)
        name = loggable(str(obj.name))
        if sha is not None and (file_key := self.files.get(sha)) is not None:
            self.key(obj, AI_PACKAGE_TYPE, file_key)
            return
        held = self.held.get(sha or "", [])
        if len(held) == 1:
            written = self.key(obj, AI_PACKAGE_TYPE, held[0])
            self.note(
                obj, written, (MODEL_FILE_ENTRY_KEY_INFO, (name, loggable(held[0])))
            )
            return
        self.note(obj, own, (MODEL_NAME_KEY_INFO, (name,)))


def import_keys(registry: IdRegistry, objects: Iterable[Any]) -> ImportPlan:
    """The key each file, dataset package and model of the imported
    *objects* is written under, by spdxId, and the ``INFO:`` lines due.

    A file not held by its name with its SHA-256: the one held layout
    alias recording it (:func:`_file_alias`), else its name. A dataset
    package: :func:`_dataset_key`. A model: the key of the one
    ``software_File`` of *objects* with its SHA-256 (that file's written
    key), the key every run looks the model up by; else of the one held
    ``software_File`` entry recording it (one
    :data:`MODEL_FILE_ENTRY_KEY_INFO`); with neither, or no SHA-256 of its
    own, its name (one :data:`MODEL_NAME_KEY_INFO`). Each note is logged by
    :func:`report_imported` only when its element is written.
    """
    objects = list(objects)
    planner = _Planner(registry, objects)
    for obj in objects:
        own = _element_key_of(obj)
        if own is not None and own[0] == DATASET_PACKAGE_TYPE:
            planner.dataset(obj, str(obj.name))
        elif own is not None and own[0] == AI_PACKAGE_TYPE:
            planner.model(obj, own)
    return ImportPlan(
        planner.keys,
        tuple(planner.notes),
        tuple(planner.aliased),
        frozenset(planner.over_changed),
    )


def report_imported(registry: IdRegistry, plan: ImportPlan) -> None:
    """Log *plan*'s notes for the elements the import wrote, one
    :data:`~pitloom.id_registry.keys.LAYOUT_ALIAS_HITS_INFO` counting the
    files written under a layout alias and one
    :data:`FILE_ALIAS_OVER_CHANGED_INFO` counting those of them whose own
    key holds other content. An element not written was skipped with its
    own line (R-keep, ambiguity, an unencodable name)."""

    def written(spdx_id: str, key: tuple[str, str]) -> bool:
        entry = registry.elements.get(key)
        return entry is not None and entry.spdx_id == spdx_id

    for note in plan.notes:
        if written(note.spdx_id, note.key):
            log.info(note.message, *note.args)
    hits = [spdx_id for spdx_id, key in plan.aliased if written(spdx_id, key)]
    if hits:
        log.info(LAYOUT_ALIAS_HITS_INFO, len(hits))
    over = sum(spdx_id in plan.over_changed for spdx_id in hits)
    if over:
        log.info(FILE_ALIAS_OVER_CHANGED_INFO, over)
