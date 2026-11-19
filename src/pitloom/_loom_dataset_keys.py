# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A loom dataset package's digest, the comment its Merkle root carries,
and the messages of its registry lookup, shared by loom and ``loom id
generate -e``; and what loom records of the digest beside the hash (its
size and the evidence of each, :func:`digest_evidence`).

See also: :mod:`pitloom._loom_dataset` (the elements) and
:mod:`pitloom.core.dataset_hash` (hashing).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._loom_caller import pointer_provenance
from pitloom.core.dataset_hash import DatasetDigest, hash_dataset
from pitloom.core.evidence import (
    BYTE_SIZE_FIELD,
    DECLARED,
    MEASURED_READ,
    MEASURED_STAT,
    Fact,
    count_fact,
    record_fact,
)
from pitloom.core.untrusted_text import escape_display_controls
from pitloom.id_registry import (
    DATASET_PACKAGE_TYPE,
    IdRegistry,
    LookupKey,
    registry_file_path,
)
from pitloom.id_registry.import_keys import name_key_reason
from pitloom.messages import emit
from pitloom.messages.id_registry_ids import (
    HASHLESS_PIN_LINE,
    REGISTRY_HASH_MISSING,
    UNGATED_LINE,
    info_name_key,
)

log = logging.getLogger("pitloom.loom")

__all__ = [
    "DigestEvidence",
    "dataset_digest",
    "digest_evidence",
    "info_key",
    "merkle_root_comment",
    "name_key_reason",
    "record_size",
]


def _files(count: int) -> str:
    return "1 file" if count == 1 else f"{count} files"


def merkle_root_comment(file_count: int, pointers: int = 0) -> str:
    """The ``Hash.comment`` of a directory dataset's Merkle root, *pointers*
    of whose files are Git LFS pointers (hashed by their ``oid``)."""
    comment = (
        f"SHA-256 Merkle root over {_files(file_count)} (path and content) in "
        "dataset directory, not a hash of a single artifact"
    )
    if pointers:
        comment += f"; Git LFS pointer oid for {_files(pointers)}; content not read"
    return comment


def dataset_digest(
    registry: IdRegistry | None, path: Path, *, max_bytes: int, sha512: bool = False
) -> DatasetDigest:
    """The digest a dataset package at *path* carries and is looked up by
    (:func:`~pitloom.core.dataset_hash.hash_dataset` within *max_bytes*),
    *registry*'s own file left out of a directory: loom and ``id generate
    -e`` both hash through here, so they cannot disagree. *sha512* (loom,
    whose SBOM describes the file) adds a file's SHA-512 from the same read;
    the lookup key is the SHA-256 either way."""
    return hash_dataset(
        path, max_bytes=max_bytes, exclude=registry_file_path(registry), sha512=sha512
    )


def info_key(
    registry: IdRegistry,
    name: str,
    lookup: LookupKey,
    digest: str | None,
    registered: str | None,
) -> None:
    """The one ``INFO:`` for a dataset package not keyed by its path or
    not gated by its content, if any: keyed by its name
    (``registry-path-key-unusable``), looked up ungated or matched a pin
    recording no hash (``registry-hash-missing``)."""
    key = lookup.key
    if not lookup.path:
        info_name_key(log, "dataset", key, name_key_reason(name))
    elif digest is None:
        emit(log, REGISTRY_HASH_MISSING, logging.INFO, line=UNGATED_LINE, entity=key)
    elif registered is not None and digest not in _held_hashes(registry, lookup.key):
        emit(
            log,
            REGISTRY_HASH_MISSING,
            logging.INFO,
            line=HASHLESS_PIN_LINE,
            entity=key,
        )


def _held_hashes(registry: IdRegistry, key: str) -> set[str | None]:
    """The hashes held for the dataset *key*, as given and display-escaped
    (the spellings a lookup tries)."""
    spellings = (key, escape_display_controls(key))
    return {
        entry.sha256
        for entry in (registry.get(DATASET_PACKAGE_TYPE, s) for s in spellings)
        if entry is not None
    }


@dataclass(frozen=True)
class DigestEvidence:
    """What a loom dataset package records of its digest beside the hash.

    Attributes:
        hash: Its ``verifiedUsing``: read in full (``measured_read``),
            copied from a Git LFS pointer's ``oid`` (``declared``), or
            ``not_measured`` with the reason it was not read (over the cap,
            a file unreadable, a directory unlistable); ``None`` for no hash
            and no reason.
        size: Its ``dataset_datasetSize``, in bytes: the bytes hashed
            (``measured_read``), the ``stat()`` size of a file not read
            (``measured_stat``), or ``not_measured`` (withheld for a file not
            read that may be a pointer, or over the largest integer
            canonical JSON writes); ``None`` for no size and no entry.
    """

    hash: Fact[str] | None = None
    size: Fact[int] | None = None

    @property
    def hash_provenance(self) -> str | None:
        """The provenance of :attr:`hash`; a declared one (the pointer's)
        keeps the pointer's ``Method:`` form."""
        if self.hash is None:
            return None
        if self.hash.level == DECLARED and self.hash.source is not None:
            return pointer_provenance(self.hash.source)
        return self.hash.provenance()

    @property
    def size_provenance(self) -> str | None:
        """The provenance of :attr:`size` (``byte_size``)."""
        return None if self.size is None else self.size.provenance()


def digest_evidence(found: DatasetDigest, label: str) -> DigestEvidence:
    """What the dataset package of *found*, the file or directory *label*
    names (:func:`~pitloom._loom_caller.cwd_relative_label`), records of it
    beside the hash: the one place its evidence level is decided. A Git LFS
    pointer: its hash declared and no size (the pointer's own is not the
    content's). Not read, for the reason *found* gives (over the cap, a file
    unreadable, a directory unlistable): the hash ``not_measured`` with that
    reason, and a file's ``stat()`` size when known; a file with none (it may
    be a pointer, or its ``stat()`` failed) gets a ``not_measured`` size.
    Hashed: the size read. Else (absent, empty, gone since found: no reason)
    nothing. A directory has no size and no size entry."""
    hex_digest = found.hex_digest
    if found.lfs_pointers and hex_digest is not None:
        return DigestEvidence(Fact.declared(hex_digest, label))
    if found.omitted is not None:
        unread: Fact[str] = Fact.not_measured(label, found.omitted)
        if found.size is not None:
            size = count_fact(found.size, MEASURED_STAT, label, BYTE_SIZE_FIELD)
            return DigestEvidence(unread, size)
        no_size: Fact[int] = Fact.not_measured(label, found.omitted)
        return DigestEvidence(unread, no_size if found.kind == "file" else None)
    if hex_digest is None:
        return DigestEvidence()
    read = Fact.measured_read(hex_digest)
    if found.size is None:
        return DigestEvidence(read)
    return DigestEvidence(
        read, count_fact(found.size, MEASURED_READ, label, BYTE_SIZE_FIELD)
    )


def record_size(
    package: spdx3.dataset_DatasetPackage,
    provenance: dict[str, str],
    evidence: DigestEvidence,
) -> None:
    """Record *evidence*'s size on *package* and in its *provenance*, after
    what its sources stated (:func:`~pitloom.core.evidence.record_fact`): a
    measured size replaces a stated one and its provenance; a
    ``not_measured`` one leaves a stated size and its provenance."""

    def set_size(size: int) -> None:
        package.dataset_datasetSize = size

    record_fact(provenance, BYTE_SIZE_FIELD, evidence.size, set_size)
