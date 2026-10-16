# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Loom ID registry hits for a document's files and directories, resolved
before any id is minted.

See also: :mod:`pitloom.assemble.spdx3._document_files` (the file
elements), :func:`pitloom.id_registry.keys.file_lookup_key` (the one key
rule every surface shares).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pitloom.core.document import DocumentModel
from pitloom.core.project import FilesOrigin, ProjectFile
from pitloom.id_registry import FILE_TYPE, IdRegistry, IdRegistrySession
from pitloom.id_registry.keys import LookupKey, file_lookup_key, project_prefix

log = logging.getLogger("pitloom.id_registry")

__all__ = ["FALLBACK_KEYS_INFO", "FileHits", "file_keys", "resolve_file_hits"]


def _resolve_directory_hits_for_file(
    dist_path: Path,
    session: IdRegistrySession,
    dir_hits: dict[str, str],
    seen_dirs: set[str],
) -> None:
    """Resolve and claim a registry hit for each not-yet-seen ancestor
    directory of *dist_path* (root-to-leaf), updating *dir_hits* in
    place.

    *seen_dirs* remembers every directory this pass has already resolved
    -- hit, rejected by *session*, or lookup miss -- so a directory
    shared by many files (the common case) is looked up and claimed at
    most once. Checking membership in *dir_hits* instead would miss the
    rejected/miss cases (neither adds a *dir_hits* entry), so every
    later file under that directory would re-look it up and, on a
    rejection, re-log the same collision ``WARNING:`` once per file
    instead of once per directory. Split out of
    :func:`_resolve_file_and_directory_hits` to keep its own cognitive
    complexity down.
    """
    for directory_path in list(dist_path.parents)[::-1]:
        directory_name = directory_path.as_posix()
        if not directory_path.name or directory_name in seen_dirs:
            continue
        seen_dirs.add(directory_name)
        claimed_id = session.lookup_id(directory_name, FILE_TYPE, [directory_name])
        if claimed_id is not None:
            dir_hits[directory_name] = claimed_id


#: The one ``INFO:`` for a document's files keyed by their path as read,
#: not from the registry's root: the count and the reason.
FALLBACK_KEYS_INFO = "ID registry: %d file(s) keyed by their path as read: %s"
_OUTSIDE_ROOT = "the project is outside the registry's root"
_NO_JOIN = "their path is outside the registry's root"
_NO_JOIN_ARCHIVE = "their path leads outside the archive's project"


def _doc_prefix(doc: DocumentModel, registry: IdRegistry) -> str | None:
    """*doc*'s project prefix in *registry*
    (:func:`~pitloom.id_registry.keys.project_prefix` of
    ``doc.files_origin.project_dir``); ``None`` without a project directory
    or outside the root."""
    project_dir = doc.files_origin.project_dir
    return None if project_dir is None else project_prefix(registry, project_dir)


def _fallback_reason(doc: DocumentModel, prefix: str | None) -> str:
    """Why some of *doc*'s files got no path key (:data:`FALLBACK_KEYS_INFO`)."""
    if doc.files_origin.archive:
        return _NO_JOIN_ARCHIVE
    return _OUTSIDE_ROOT if prefix is None else _NO_JOIN


def _file_keys(
    doc: DocumentModel, prefix: str | None, registry: IdRegistry
) -> dict[str, LookupKey]:
    """:func:`file_keys` given *doc*'s project *prefix*."""
    origin = doc.files_origin
    keys = {
        pf.distribution_path: file_lookup_key(pf, origin, prefix, registry)
        for pf in doc.project.files
    }
    fallbacks = sum(not lookup.path for lookup in keys.values())
    if fallbacks and (origin.project_dir is not None or origin.archive):
        log.info(FALLBACK_KEYS_INFO, fallbacks, _fallback_reason(doc, prefix))
    return keys


def file_keys(doc: DocumentModel, registry: IdRegistry) -> dict[str, LookupKey]:
    """Each of *doc*'s files' registry key in *registry*
    (:func:`~pitloom.id_registry.keys.file_lookup_key`), by
    ``distribution_path``. The project prefix is computed once, from
    ``doc.files_origin.project_dir``. When files of a document naming its
    origin get no path key, one ``INFO:`` (:data:`FALLBACK_KEYS_INFO`)
    gives their count and why."""
    return _file_keys(doc, _doc_prefix(doc, registry), registry)


def _resolve_file_and_directory_hits(
    files: list[ProjectFile],
    session: IdRegistrySession,
    keys: Mapping[str, LookupKey] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Pre-resolve every file's and directory's registry hit in one pass
    over *files*, before any minting starts.

    Each file is looked up once, by its key in *keys* (:func:`file_keys`;
    by default, :func:`~pitloom.id_registry.keys.file_lookup_key` with no
    origin and no project prefix), gated by its SHA-256. Returns
    ``(dir_hits, file_hits)``: *dir_hits* keyed by directory name
    (as :func:`_ensure_directory_chain` computes it, POSIX-style
    parent-path segment), *file_hits* keyed by ``distribution_path``. Both
    empty when *session* has no registry loaded. Callers must reserve
    every value in both dicts (:func:`~pitloom.core.models.reserve_spdx_ids`)
    before minting anything, then pass these dicts down instead of the
    registry itself: pre-resolution is the single source of truth for
    which ids were reserved, so the actual build must never look the
    registry up a second time and risk a different answer.

    *files* is walked in its own given order, and each file's directories
    root-to-leaf, so hit resolution is deterministic; when a directory or
    file's registry hit is an id something earlier in this same pass (or
    an earlier file/directory/AI-model hit in the same document, via the
    shared *session*) already claimed, only the first claimant reuses it
    -- a later one falls back to a fresh mint instead of duplicating the
    id, with one ``WARNING: ID registry: ...`` naming both.
    """
    dir_hits: dict[str, str] = {}
    file_hits: dict[str, str] = {}
    if session.registry is None:
        return dir_hits, file_hits
    seen_dirs: set[str] = set()
    keys = keys or {}

    for package_file in files:
        dist_path = Path(package_file.distribution_path)
        _resolve_directory_hits_for_file(dist_path, session, dir_hits, seen_dirs)

        lookup = keys.get(package_file.distribution_path) or file_lookup_key(
            package_file, FilesOrigin(), None
        )
        claimed_id = session.lookup_key(
            package_file.distribution_path,
            FILE_TYPE,
            lookup,
            sha256=cast(str, package_file.digest_sha256),
        )
        if claimed_id is not None:
            file_hits[package_file.distribution_path] = claimed_id

    return dir_hits, file_hits


@dataclass(frozen=True)
class FileHits:
    """One document's file and directory registry hits
    (:func:`_resolve_file_and_directory_hits`), each file's key (*keys*,
    by ``distribution_path``), the project *prefix* they were joined to
    (``None``: none) and the *session* they were claimed in."""

    session: IdRegistrySession
    dirs: dict[str, str]
    files: dict[str, str]
    keys: dict[str, LookupKey]
    prefix: str | None

    def record(self, file_spdx_ids: Mapping[str, str]) -> None:
        """Record each file's key for the id it got (*file_spdx_ids*, by
        ``distribution_path``), so a minted id is harvested under it; a
        hit's own recorded key wins
        (:meth:`~pitloom.id_registry.IdRegistrySession.record_key`)."""
        for dist_path, spdx_id in file_spdx_ids.items():
            lookup = self.keys.get(dist_path)
            if lookup is not None:
                self.session.record_key(spdx_id, FILE_TYPE, lookup.key)


def resolve_file_hits(doc: DocumentModel, session: IdRegistrySession) -> FileHits:
    """*doc*'s :class:`FileHits` in *session*."""
    registry = session.registry
    prefix = None if registry is None else _doc_prefix(doc, registry)
    keys = {} if registry is None else _file_keys(doc, prefix, registry)
    dirs, files = _resolve_file_and_directory_hits(doc.project.files, session, keys)
    return FileHits(session, dirs, files, keys, prefix)
