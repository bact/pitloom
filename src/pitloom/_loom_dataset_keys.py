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

from pitloom._loom_caller import evidence_provenance, pointer_provenance
from pitloom.core.dataset_hash import DatasetDigest, hash_dataset
from pitloom.core.evidence import MEASURED_STAT, NOT_MEASURED, OVER_CAP
from pitloom.core.untrusted_text import escape_display_controls
from pitloom.extract.dataset.values import stated_count
from pitloom.id_registry import (
    DATASET_PACKAGE_TYPE,
    IdRegistry,
    LookupKey,
    registry_file_path,
)
from pitloom.id_registry.import_keys import DATASET_NAME_KEY_INFO as NAME_KEY_INFO
from pitloom.id_registry.import_keys import name_key_reason
from pitloom.logging_config import loggable

log = logging.getLogger("pitloom.loom")

__all__ = [
    "HASHLESS_PIN_INFO",
    "NAME_KEY_INFO",
    "PIN_WITHOUT_HASH_INFO",
    "SPELLING_PIN_WARNING",
    "UNGATED_INFO",
    "DigestEvidence",
    "dataset_digest",
    "digest_evidence",
    "info_key",
    "merkle_root_comment",
    "name_key_reason",
    "record_size",
]

#: ``log.warning()`` format for a later spelling of a dataset whose registry id
#: differs from the first spelling's. Arguments: the later spelling, its pinned
#: id, the first spelling.
SPELLING_PIN_WARNING = (
    "ID registry: dataset %s is pinned to %s, but it is read as %s, whose id is used"
)

#: ``log.info()`` formats for a dataset package keyed or gated otherwise than
#: by its path and content, each said once per package per run (loom) or per
#: pin (``id generate -e``). Arguments: the key, then (where taken) why.
PIN_WITHOUT_HASH_INFO = "ID registry: dataset %s pinned without SHA-256: %s"
HASHLESS_PIN_INFO = (
    "ID registry: dataset %s matched a pin without SHA-256; content not checked"
)
UNGATED_INFO = "ID registry: dataset %s looked up ungated: not hashed"


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
    not gated by its content, if any: keyed by its name, looked up ungated,
    or matched a pin recording no hash."""
    key = loggable(lookup.key)
    if not lookup.path:
        log.info(NAME_KEY_INFO, key, name_key_reason(name))
    elif digest is None:
        log.info(UNGATED_INFO, key)
    elif registered is not None and digest not in _held_hashes(registry, lookup.key):
        log.info(HASHLESS_PIN_INFO, key)


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
        hash_provenance: The provenance of its ``verifiedUsing``: copied
            from a Git LFS pointer, or ``not_measured`` over the cap;
            ``None`` for a hash read in full and for no hash.
        size: Its ``dataset_datasetSize``, in bytes; ``None`` when none.
        size_provenance: The provenance of *size* (``byte_size``):
            ``measured_stat``, or ``not_measured`` over the largest integer
            canonical JSON writes; ``None`` for a size read in full and for
            no size.
    """

    hash_provenance: str | None = None
    size: int | None = None
    size_provenance: str | None = None


def digest_evidence(found: DatasetDigest, label: str) -> DigestEvidence:
    """What the dataset package of *found*, the file or directory *label*
    names (:func:`~pitloom._loom_caller.cwd_relative_label`), records of it
    beside the hash: the one place its evidence level is decided. A Git LFS
    pointer: the pointer's provenance and no size (the pointer's own is not
    the content's). Over the cap: the hash ``not_measured``, and a file's
    ``stat()`` size when known. Hashed: the size read (no provenance). Else
    (not hashed for any other reason) nothing. A directory has no size."""
    if found.lfs_pointers:
        return DigestEvidence(pointer_provenance(label))
    if found.omitted == OVER_CAP:
        unread = evidence_provenance(label, NOT_MEASURED, OVER_CAP)
        if found.size is None:
            return DigestEvidence(unread)
        return DigestEvidence(unread, *_bounded_size(found.size, label, MEASURED_STAT))
    if found.hex_digest is not None:
        return _read_size(found, label)
    return DigestEvidence()


def _read_size(found: DatasetDigest, label: str) -> DigestEvidence:
    """The size of the file *found* hashed: the bytes read, with no
    provenance (``measured_read`` writes none)."""
    if found.size is None:
        return DigestEvidence()
    return DigestEvidence(None, *_bounded_size(found.size, label, None))


def _bounded_size(
    size: int, label: str, level: str | None
) -> tuple[int | None, str | None]:
    """*size* and its provenance at the evidence *level* (``None``: none);
    over the largest integer canonical JSON writes, no size and
    ``not_measured``, with the over-cap ``WARNING:`` of every byte size."""
    if stated_count(size, label, "byte_size") is None:
        return None, evidence_provenance(label, NOT_MEASURED, OVER_CAP)
    return size, None if level is None else evidence_provenance(label, level)


def record_size(
    package: spdx3.dataset_DatasetPackage,
    provenance: dict[str, str],
    evidence: DigestEvidence,
) -> None:
    """Record *evidence*'s size on *package* and in its *provenance*, after
    what its sources stated: a measured size replaces a stated one and its
    provenance (a declared size loses to a measured one, evidence-levels
    Rule 1; no loom source states one yet); with none measured, a stated
    size stands with its own provenance."""
    if evidence.size is not None:
        package.dataset_datasetSize = evidence.size
        provenance.pop("byte_size", None)
    if evidence.size_provenance is not None and "byte_size" not in provenance:
        provenance["byte_size"] = evidence.size_provenance
