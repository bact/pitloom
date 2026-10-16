# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Index the files under a project into an :class:`IdRegistry`.

See also: :meth:`pitloom.id_registry._registry.IdRegistry.generate`, which
delegates here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from pitloom.core.file_identity import file_id
from pitloom.id_registry._types import (
    AI_PACKAGE_TYPE,
    FILE_TYPE,
    NFC_CLASH_WARNING,
    _element_key,
    _iter_files,
    _unstorable_name_error,
    sha256_file,
    warn_unreadable_file,
)
from pitloom.id_registry.import_keys import LAYOUT_ALIAS_CHANGED_INFO
from pitloom.id_registry.keys import (
    LAYOUT_ALIAS_PROMOTED_INFO,
    alias_candidates,
    alias_tail,
    join_key,
    on_disk_path,
    path_key,
    project_prefix,
)
from pitloom.logging_config import loggable

if TYPE_CHECKING:
    from pitloom.id_registry._registry import IdRegistry

log = logging.getLogger("pitloom.id_registry")

__all__ = ["index_files"]


class _Indexed(NamedTuple):
    """A file to register: its *path*, registry *key* and *sha256*."""

    path: Path
    key: str
    sha256: str


def _file_key(
    scope: IdRegistry, prefix: str, file_path: Path, project_root: Path
) -> str:
    """The key of *file_path*: its path from *project_root* (*scope* is a
    registry rooted there), joined to the project's *prefix*. A file outside
    the project is a ``ValueError`` naming both."""
    rel = path_key(scope, file_path)
    key = None if rel is None else join_key(prefix, rel)
    if key is None:
        raise ValueError(
            f"ID registry: {loggable(str(file_path))} is outside the "
            f"project root {loggable(str(project_root))}"
        )
    return key


def _one_file_per_key(indexed: list[_Indexed]) -> list[_Indexed]:
    """*indexed* with one entry per key, in walk order. A key held by
    several distinct files (two spellings of one name, possible where the
    file system keeps both) gets one ``WARNING:`` and none: neither stands
    for it, and each would re-mint the other's id. One file named twice
    (``d/../d/a.txt``) is one."""
    by_key: dict[str, list[_Indexed]] = {}
    for item in indexed:
        by_key.setdefault(item.key, []).append(item)
    kept: list[_Indexed] = []
    for key, group in by_key.items():
        files = {file_id(item.path) or item.path for item in group}
        if len(files) > 1:
            log.warning(NFC_CLASH_WARNING, len(files), loggable(key))
        else:
            kept.append(group[0])
    return kept


class _Scope(NamedTuple):
    """Where a walk's keys are from: *root*, the directory they are paths
    from, and *base*, the project prefix below which a layout alias is
    taken (:func:`~pitloom.id_registry.keys.alias_tail`)."""

    root: Path
    base: str


class _Promoted(NamedTuple):
    """How many keys :func:`_promote_alias` moved: to a new key (*added*),
    and over a held key of other content (*changed*)."""

    added: int = 0
    changed: int = 0


def _promote_alias(
    registry: IdRegistry,
    type_name: str,
    item: _Indexed,
    walked: frozenset[str],
    scope: _Scope,
) -> _Promoted:
    """When *item*'s :func:`~pitloom.id_registry.keys.alias_tail` below
    ``scope.base`` is a held key of *type_name* with *item*'s hash
    (:func:`~pitloom.id_registry.keys.alias_candidates`, paths from
    ``scope.root``) and *item*'s key is new or holds other content (which
    :meth:`IdRegistry.register` would re-mint), move that entry to the key
    (its id is kept; a replaced id stays reserved), as a run's lookup hits
    the alias. Only that direction: a longer held key is never moved to a
    shorter one. A key of another walked file is a file of its own, never
    the alias."""
    tail = alias_tail(item.key, scope.base)
    if tail is None or tail in walked:
        return _Promoted()
    own = registry.get(type_name, item.key)
    if own is not None and own.sha256 == item.sha256:
        return _Promoted()
    held = alias_candidates(
        registry, type_name, item.key, item.sha256, root=scope.root, base=scope.base
    )
    if tail not in held:
        return _Promoted()
    if own is not None:
        registry.reserve_id(own.spdx_id)
        del registry.elements[_element_key(type_name=type_name, name=item.key)]
    moved = int(registry.promote_alias(type_name, tail, item.key))
    return _Promoted(changed=moved) if own is not None else _Promoted(added=moved)


def _is_model(path: Path) -> bool:
    """Whether a project scan lists the file at *path* as an AI model: the
    scan's suffix filter, then its header."""
    # pylint: disable=import-outside-toplevel,cyclic-import
    from pitloom.extract.ai_model import AiModelFormat, detect_ai_model_format
    from pitloom.extract.scanner import is_model_candidate_name

    return (
        is_model_candidate_name(path.name)
        and detect_ai_model_format(path) != AiModelFormat.UNKNOWN
    )


def _walk_indexed(
    registry: IdRegistry,
    paths: list[Path],
    project_root: Path,
    exclude: Path | None,
    explicit: bool,
    prefix: str,
) -> list[_Indexed]:
    """The readable, storable files under *paths* with their keys (joined
    to the project's *prefix*) and hashes, in walk order; each that is not
    gets a warning."""
    # pylint: disable-next=import-outside-toplevel,cyclic-import
    from pitloom.id_registry._registry import IdRegistry as Registry

    # The project's own root is the base of every file's path. Each walk
    # root is spelt as the file system lists it, once; the names the walk
    # lists below it are already.
    scope = Registry(registry.namespace, project_root=project_root)
    spelt = [
        on_disk_path(project_root, path if path.is_absolute() else project_root / path)
        for path in paths
    ]
    indexed: list[_Indexed] = []
    for file_path in _iter_files(spelt, project_root, exclude, explicit=explicit):
        try:
            sha256 = sha256_file(file_path)
        except OSError as exc:
            warn_unreadable_file(file_path, project_root, exc)
            continue
        key = _file_key(scope, prefix, file_path, project_root)
        name_error = _unstorable_name_error(file_path, project_root)
        if name_error is not None:
            warn_unreadable_file(file_path, project_root, name_error)
            continue
        indexed.append(_Indexed(file_path, key, sha256))
    return indexed


def index_files(
    registry: IdRegistry,
    paths: list[Path],
    project_root: Path,
    exclude: Path | None,
    *,
    explicit: bool = True,
) -> None:
    """Register the files under *paths* (and their AI models) in *registry*,
    except the *exclude* file; see :meth:`IdRegistry.generate`. *explicit*
    is false for implicit default roots (see
    :func:`~pitloom.id_registry._types._iter_files`)."""
    prefix = project_prefix(registry, project_root)
    indexed = _walk_indexed(
        registry, paths, project_root, exclude, explicit, prefix or ""
    )
    walked = frozenset(item.key for item in indexed)
    # The keys are paths from the registry's root, or from a project outside.
    scope = (
        _Scope(project_root, "")
        if prefix is None
        else _Scope(registry.root_dir(), prefix)
    )
    added = changed = 0
    for item in _one_file_per_key(indexed):
        # A model's package has its file's key and hash (the one model rule).
        types = (FILE_TYPE, AI_PACKAGE_TYPE) if _is_model(item.path) else (FILE_TYPE,)
        for type_name in types:
            moved = _promote_alias(registry, type_name, item, walked, scope)
            added, changed = added + moved.added, changed + moved.changed
            registry.register(type_name, item.key, sha256=item.sha256)
    if added:
        log.info(LAYOUT_ALIAS_PROMOTED_INFO, added)
    if changed:
        log.info(LAYOUT_ALIAS_CHANGED_INFO, changed)
