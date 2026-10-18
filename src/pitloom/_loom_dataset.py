# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A loom dataset as SPDX elements: a ``dataset_DatasetPackage`` and, for a
single regular file, the ``software_File`` it ``contains``.

A package is keyed by the dataset's path from the registry's project root
when that path exists below it at declaration
(:func:`~pitloom.id_registry.artifact_key`: on-disk spelling, NFC), else by
the caller's name. Its lookup is gated by the package's digest (a file's
SHA-256, a directory's Merkle root, :func:`dataset_digest`), except that an
entry recording no hash (an explicit pin) is a hit for any content; with no
digest (missing, over the ceiling, unreadable), it is ungated. A refreshed
dataset, a file added to a directory included, is a new package id. A file
is named and looked up by its path key (on-disk spelling), gated by its
SHA-256. A single file's package and ``software_File`` (and the script's
file) state its SHA-256 and SHA-512, from one read; a directory gets its
Merkle root (SHA-256 only) and no file elements. Loom never
writes these entries to the registry (only models, :mod:`pitloom._loom_model`).

See also: :mod:`pitloom._loom_active_run` (the run) and
:mod:`pitloom.core.dataset_hash` (hashing).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import cast

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._loom_caller import LOOM_PROVENANCE_CONFIG, registry_miss_callback
from pitloom._loom_dataset_meta import (
    DatasetDoc,
    DatasetSources,
    escape_display_text,
    write_metadata,
)
from pitloom.assemble.spdx3.provenance import emit_provenance
from pitloom.core.dataset_hash import DatasetDigest, hash_dataset
from pitloom.core.file_hash import HexDigests, file_digests
from pitloom.core.models import build_relationship, generate_spdx_id
from pitloom.core.path_probe import (
    UNREADABLE_FILE_WARNING,
    is_missing_errno,
    is_regular_file,
)
from pitloom.core.untrusted_text import escape_display_controls
from pitloom.export.spdx3_json import (
    Spdx3JsonExporter,
    file_hashes,
    require_spdx_id,
    sha256_hash,
)
from pitloom.id_registry import (
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    Alias,
    IdRegistry,
    IdRegistrySession,
    LookupKey,
    artifact_key,
    path_key,
    registry_file_path,
)
from pitloom.id_registry.import_keys import DATASET_NAME_KEY_INFO as NAME_KEY_INFO
from pitloom.id_registry.import_keys import name_key_reason
from pitloom.logging_config import loggable, one_line

log = logging.getLogger("pitloom.loom")

__all__ = [
    "HASHLESS_PIN_INFO",
    "NAME_KEY_INFO",
    "OUTSIDE_ROOT_WARNING",
    "PIN_WITHOUT_HASH_INFO",
    "REGISTRY_IN_DATASET_WARNING",
    "UNGATED_INFO",
    "LoomElements",
    "dataset_digest",
    "merkle_root_comment",
    "name_key_reason",
]

#: ``log.warning()`` format for a file outside the registry's project root.
#: Arguments: the path as the caller gave it, the root.
OUTSIDE_ROOT_WARNING = (
    "loom: file %r is outside the ID registry's project root %s; minting a new spdxId"
)
#: ``log.warning()`` format for the declared registry inside a directory
#: dataset. Arguments: the registry path, the dataset's name.
REGISTRY_IN_DATASET_WARNING = (
    "loom: ID registry %s is inside dataset directory %r; left out of its Merkle root"
)

#: ``log.info()`` formats for a dataset package keyed or gated otherwise than
#: by its path and content, each said once per package per run (loom) or per
#: pin (``id generate -e``). Arguments: the key, then (where taken) why.
PIN_WITHOUT_HASH_INFO = "ID registry: dataset %s pinned without SHA-256: %s"
HASHLESS_PIN_INFO = (
    "ID registry: dataset %s matched a pin without SHA-256; content not checked"
)
UNGATED_INFO = "ID registry: dataset %s looked up ungated: not hashed"


def merkle_root_comment(file_count: int) -> str:
    """The ``Hash.comment`` of a directory dataset's Merkle root."""
    files = "1 file" if file_count == 1 else f"{file_count} files"
    return (
        f"SHA-256 Merkle root over {files} (path and content) in dataset "
        "directory, not a hash of a single artifact"
    )


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


def _info_key(
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


def _dataset_kind(dataset_type: str) -> str:
    """The ``dataset_DatasetType`` term for *dataset_type* (``text`` when
    it names none)."""
    return cast(
        str,
        getattr(
            spdx3.dataset_DatasetType, dataset_type, spdx3.dataset_DatasetType.text
        ),
    )


class LoomElements:
    """The dataset and file elements of one loom run, added to its document.

    Holds the run's caches: one ``dataset_DatasetPackage`` per key and
    content and one ``software_File`` per path key and content, so a
    dataset declared twice (``add_input_dataset`` then ``add_dataset``, or
    under two spellings of one path) is one element and one registry
    claim; the names each package was declared under; and the paths
    already warned to be outside the registry's project root.
    """

    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        *,
        session: IdRegistrySession,
        exporter: Spdx3JsonExporter,
        creation_info: spdx3.CreationInfo,
        doc_uuid: str,
        max_hash_bytes: int,
    ) -> None:
        self._session = session
        self._exporter = exporter
        self._creation_info = creation_info
        self._doc_uuid = doc_uuid
        self._max_hash_bytes = max_hash_bytes
        self._files: dict[tuple[str, str | None], spdx3.software_File] = {}
        self._packages: dict[
            tuple[LookupKey, str | None], spdx3.dataset_DatasetPackage
        ] = {}
        self._declared: list[tuple[str, spdx3.dataset_DatasetPackage]] = []
        self._outside_warned: set[str] = set()
        self._left_out_warned: set[str] = set()
        # Per package (by identity), written by finish(): it, its caller
        # provenance, the id of its provenance Annotation (minted with the
        # package, so the ids do not depend on what the run declares
        # later), and what its sources state.
        self._details: dict[
            int, tuple[spdx3.dataset_DatasetPackage, str, str, DatasetSources]
        ] = {}
        # The packages whose data_preprocessing a call declared.
        self._preprocessing_declared: set[int] = set()

    def dataset(
        self,
        name: str,
        dataset_type: str,
        caller_info: str,
        sources: DatasetSources | None = None,
    ) -> spdx3.dataset_DatasetPackage:
        """The ``dataset_DatasetPackage`` for *name*, with what it holds.

        The package is named *name* as first declared. A regular file gets
        its own ``software_File`` and a ``contains`` edge to it, each
        element with its own ``Hash``; a directory, its Merkle root. One
        key (:meth:`_package_key`) holding one content is one package per
        run, whatever declares it: a repeat adds only a new *dataset_type*
        and its *sources*, after the earlier declarations' (merged by
        :meth:`finish`).
        """
        registry = self._session.registry
        found = dataset_digest(
            registry, Path(name), max_bytes=self._max_hash_bytes, sha512=True
        )
        if found.excluded:  # said even when no root came of the directory
            self._warn_registry_in(name)
        lookup = self._package_key(name)
        held_package = self._packages.get((lookup, found.hex_digest))
        if held_package is not None:
            self._declared.append((name, held_package))
            if sources is not None:
                self._details[id(held_package)][3].extend(sources)
            return self._add_kind(held_package, dataset_type)
        package = self._package(name, lookup, found.hex_digest)
        annotation_id = generate_spdx_id("Annotation", name, self._doc_uuid)
        self._details[id(package)] = (
            package,
            caller_info,
            annotation_id,
            sources or DatasetSources(),
        )
        package.dataset_datasetType = [_dataset_kind(dataset_type)]
        self._packages[(lookup, found.hex_digest)] = package
        self._declared.append((name, package))
        if found.hex_digest is None:
            return package
        if found.kind == "dir":
            comment = merkle_root_comment(found.file_count)
            package.verifiedUsing = [sha256_hash(found.hex_digest, comment=comment)]
            return package
        digests = HexDigests(found.hex_digest, found.hex_sha512)
        package.verifiedUsing = file_hashes(digests)
        held = self.file(name, Path(name), digests)
        # build_relationship() gives None only for a None from_id.
        relationship = build_relationship(
            from_id=require_spdx_id(package),
            to_ids=[require_spdx_id(held)],
            rel_type=spdx3.RelationshipType.contains,
            doc_name="loom",
            doc_uuid=self._doc_uuid,
            creation_info=self._creation_info,
        )
        self._exporter.add_relationship(cast(spdx3.Relationship, relationship))
        return package

    def declare_preprocessing(self, package: spdx3.dataset_DatasetPackage) -> None:
        """Record that a call declared *package*'s ``data_preprocessing``
        (even ``[]``): no source's replaces it."""
        self._preprocessing_declared.add(id(package))

    def finish(self) -> None:
        """Write each package's metadata and its one provenance record (the
        declaring caller, then each field a source stated)."""
        doc = DatasetDoc(
            self._exporter, self._creation_info, self._doc_uuid, LOOM_PROVENANCE_CONFIG
        )
        for package, caller_info, annotation_id, sources in self._details.values():
            provenance = {"package": caller_info}
            written: list[tuple[str, spdx3.Element]] = []
            meta = sources.merged(str(package.name))
            if meta is not None:
                stated, written = write_metadata(
                    package,
                    meta,
                    doc,
                    preprocessing_declared=id(package) in self._preprocessing_declared,
                )
                provenance.update(stated)
            emit_provenance(
                subject=package,
                provenance=provenance,
                creation_info=self._creation_info,
                doc_name=str(package.name),
                doc_uuid=self._doc_uuid,
                exporter=self._exporter,
                provenance_config=LOOM_PROVENANCE_CONFIG,
                annotation_spdx_id=annotation_id,
            )
            if written:
                escape_display_text(str(package.name), written)

    def names_of(self, package: spdx3.dataset_DatasetPackage) -> list[str]:
        """Every name *package* was declared under, in order, once each:
        ``add_output_dataset(input_datasets=...)`` matches any of them."""
        return list(dict.fromkeys(n for n, held in self._declared if held is package))

    def _package_key(self, name: str) -> LookupKey:
        """The key of the dataset *name*: its path key when it exists below
        the registry's root, else *name* (and with no registry)."""
        registry = self._session.registry
        if registry is None:
            return LookupKey(name)
        return artifact_key(registry, path=name, name=name)

    @staticmethod
    def _add_kind(
        package: spdx3.dataset_DatasetPackage, dataset_type: str
    ) -> spdx3.dataset_DatasetPackage:
        """*package* with *dataset_type* among its kinds, once."""
        kind = _dataset_kind(dataset_type)
        if kind not in package.dataset_datasetType:
            package.dataset_datasetType = [*package.dataset_datasetType, kind]
        return package

    def script_file(self, name: str, path: Path) -> spdx3.software_File:
        """The ``software_File`` of the run's script: *name* as captured,
        *path* absolute (the current directory may have changed since).
        Hashed in full: the dataset ceiling does not apply."""
        digests: HexDigests | None = None
        try:
            if is_regular_file(path):
                digests = file_digests(path).hex()
        except OSError as exc:
            if not is_missing_errno(exc):
                log.warning(
                    UNREADABLE_FILE_WARNING,
                    loggable(name),
                    "for the script hash",
                    one_line(exc),
                )
        return self.file(name, path, digests)

    def file(
        self, name: str, path: Path, digests: HexDigests | None
    ) -> spdx3.software_File:
        """The run's ``software_File`` for the file at *path* holding
        *digests* (``None``: not hashed), added to the document once.

        Named by its path key (:func:`~pitloom.id_registry.path_key`,
        on-disk spelling) when it is inside the registry's project root,
        and then looked up gated by its SHA-256, its ``CANONICAL`` layout
        alias included (a ``src/`` file hits a wheel's installed path);
        else named *name*, as given, and minted.
        """
        element_name, keyed = self._file_name(name, path)
        hex_digest = None if digests is None else digests.sha256
        cached = self._files.get((element_name, hex_digest))
        if cached is not None:
            return cached
        registered = None
        if keyed and hex_digest is not None:
            registered = self._session.lookup_key(
                element_name,
                FILE_TYPE,
                LookupKey(element_name, Alias.CANONICAL, path=True),
                sha256=hex_digest,
                on_miss=registry_miss_callback(self._session, FILE_TYPE, element_name),
            )
        file_element = spdx3.software_File(
            spdxId=registered or generate_spdx_id("File", element_name, self._doc_uuid),
            name=element_name,
            creationInfo=self._creation_info,
        )
        file_element.software_fileKind = spdx3.software_FileKindType.file
        if digests is not None:
            file_element.verifiedUsing = file_hashes(digests)
        self._exporter.add_file(file_element)
        self._files[(element_name, hex_digest)] = file_element
        return file_element

    def _file_name(self, name: str, path: Path) -> tuple[str, bool]:
        """The element name of the file at *path*, and whether it is a
        registry key. Outside the project root: *name*, with one
        ``WARNING:`` per path per run."""
        registry = self._session.registry
        if registry is None:
            return name, False
        key = path_key(registry, path, on_disk=True)
        if key is not None:
            return key, True
        real = os.path.realpath(path)
        if real not in self._outside_warned:
            self._outside_warned.add(real)
            log.warning(OUTSIDE_ROOT_WARNING, name, loggable(str(registry.root_dir())))
        return name, False

    def _package(
        self, name: str, lookup: LookupKey, digest: str | None
    ) -> spdx3.dataset_DatasetPackage:
        """The ``dataset_DatasetPackage`` named *name*, looked up by
        *lookup* gated by *digest*, a hash-less pin a hit for any content
        (ungated with no *digest*)."""
        session = self._session
        registered = session.lookup_key(
            name,
            DATASET_PACKAGE_TYPE,
            lookup,
            sha256=digest,
            pin_without_hash=True,
            on_miss=registry_miss_callback(
                session, DATASET_PACKAGE_TYPE, lookup.key, by_path=lookup.path
            ),
        )
        if session.registry is not None:
            _info_key(session.registry, name, lookup, digest, registered)
        package = spdx3.dataset_DatasetPackage(
            spdxId=registered
            or generate_spdx_id("DatasetPackage", name, self._doc_uuid),
            name=name,
            creationInfo=self._creation_info,
        )
        self._exporter.add_package(package)
        return package

    def _warn_registry_in(self, name: str) -> None:
        """Warn, once per directory per run, that the declared registry was
        left out of the directory dataset *name*."""
        real = os.path.realpath(name)
        if real not in self._left_out_warned:
            self._left_out_warned.add(real)
            log.warning(
                REGISTRY_IN_DATASET_WARNING,
                loggable(str(registry_file_path(self._session.registry))),
                name,
            )
