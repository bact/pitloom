# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A loom dataset as SPDX elements: a ``dataset_DatasetPackage`` and, for a
single regular file, the ``software_File`` it ``contains``.

A package is looked up under the caller's name, ungated, whatever the dataset
is (a file, a directory, a remote name). A file is named and looked up by its
path relative to the registry's project root
(:func:`~pitloom.id_registry.registry_key_for_path`), gated by its SHA-256. A
directory gets its Merkle root and no file elements. Loom never writes these
entries to the registry (only models, :mod:`pitloom._loom_model`).

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
from pitloom.assemble.spdx3.provenance import emit_provenance
from pitloom.core.dataset_hash import hash_dataset
from pitloom.core.file_hash import sha256_digest
from pitloom.core.models import build_relationship, generate_spdx_id
from pitloom.core.path_probe import (
    UNREADABLE_FILE_WARNING,
    is_missing_errno,
    is_regular_file,
)
from pitloom.export.spdx3_json import (
    Spdx3JsonExporter,
    require_spdx_id,
    sha256_hash,
)
from pitloom.id_registry import (
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    IdRegistrySession,
    registry_file_path,
    registry_key_for_path,
)
from pitloom.logging_config import loggable, one_line

log = logging.getLogger("pitloom.loom")

__all__ = [
    "OUTSIDE_ROOT_WARNING",
    "REGISTRY_IN_DATASET_WARNING",
    "LoomElements",
    "merkle_root_comment",
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


def merkle_root_comment(file_count: int) -> str:
    """The ``Hash.comment`` of a directory dataset's Merkle root."""
    files = "1 file" if file_count == 1 else f"{file_count} files"
    return (
        f"SHA-256 Merkle root over {files} (path and content) in dataset "
        "directory, not a hash of a single artifact"
    )


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

    Holds the run's caches: one ``software_File`` per name and content, so a
    file declared twice (``add_input_dataset`` then ``add_dataset``) is one
    element and one registry claim; and the paths already warned to be
    outside the registry's project root.
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
        self._packages: dict[tuple[str, str | None], spdx3.dataset_DatasetPackage] = {}
        self._outside_warned: set[str] = set()
        self._left_out_warned: set[str] = set()

    def dataset(
        self, name: str, dataset_type: str, caller_info: str
    ) -> spdx3.dataset_DatasetPackage:
        """The ``dataset_DatasetPackage`` for *name*, with what it holds.

        *name* stays as given: ``add_output_dataset(input_datasets=...)``
        matches it. A regular file gets its own ``software_File`` and a
        ``contains`` edge to it, each element with its own ``Hash``; a
        directory, its Merkle root. The same name holding the same content
        is one package per run, whatever declares it: a repeat adds only a
        new *dataset_type*.
        """
        found = hash_dataset(
            Path(name),
            max_bytes=self._max_hash_bytes,
            exclude=registry_file_path(self._session.registry),
        )
        if found.excluded:  # said even when no root came of the directory
            self._warn_registry_in(name)
        held_package = self._packages.get((name, found.hex_digest))
        if held_package is not None:
            return self._add_kind(held_package, dataset_type)
        package = self._package(name, dataset_type, caller_info)
        self._packages[(name, found.hex_digest)] = package
        if found.hex_digest is None:
            return package
        if found.kind == "dir":
            comment = merkle_root_comment(found.file_count)
            package.verifiedUsing = [sha256_hash(found.hex_digest, comment=comment)]
            return package
        package.verifiedUsing = [sha256_hash(found.hex_digest)]
        held = self.file(name, Path(name), found.hex_digest)
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
        hex_digest: str | None = None
        try:
            if is_regular_file(path):
                hex_digest = sha256_digest(path).hex()
        except OSError as exc:
            if not is_missing_errno(exc):
                log.warning(
                    UNREADABLE_FILE_WARNING,
                    loggable(name),
                    "for the script hash",
                    one_line(exc),
                )
        return self.file(name, path, hex_digest)

    def file(
        self, name: str, path: Path, hex_digest: str | None
    ) -> spdx3.software_File:
        """The run's ``software_File`` for the file at *path* holding
        *hex_digest* (``None``: not hashed), added to the document once.

        Named by its registry key when it is inside the registry's project
        root, and then looked up gated by its SHA-256; else named *name*,
        as given, and minted.
        """
        element_name, keyed = self._file_name(name, path)
        cached = self._files.get((element_name, hex_digest))
        if cached is not None:
            return cached
        registered = None
        if keyed and hex_digest is not None:
            registered = self._session.lookup_id(
                element_name,
                FILE_TYPE,
                [element_name],
                sha256=hex_digest,
                on_miss=registry_miss_callback(self._session, FILE_TYPE, element_name),
            )
        file_element = spdx3.software_File(
            spdxId=registered or generate_spdx_id("File", element_name, self._doc_uuid),
            name=element_name,
            creationInfo=self._creation_info,
        )
        file_element.software_fileKind = spdx3.software_FileKindType.file
        if hex_digest is not None:
            file_element.verifiedUsing = [sha256_hash(hex_digest)]
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
        key = registry_key_for_path(registry, path)
        if key is not None:
            return key, True
        real = os.path.realpath(path)
        if real not in self._outside_warned:
            self._outside_warned.add(real)
            log.warning(OUTSIDE_ROOT_WARNING, name, loggable(str(registry.root_dir())))
        return name, False

    def _package(
        self, name: str, dataset_type: str, caller_info: str
    ) -> spdx3.dataset_DatasetPackage:
        """The ``dataset_DatasetPackage`` named *name*, looked up by name."""
        registered = self._session.lookup_id(
            name,
            DATASET_PACKAGE_TYPE,
            [name],
            on_miss=registry_miss_callback(self._session, DATASET_PACKAGE_TYPE, name),
        )
        package = spdx3.dataset_DatasetPackage(
            spdxId=registered
            or generate_spdx_id("DatasetPackage", name, self._doc_uuid),
            name=name,
            creationInfo=self._creation_info,
        )
        emit_provenance(
            subject=package,
            provenance={"package": caller_info},
            creation_info=self._creation_info,
            doc_name=name,
            doc_uuid=self._doc_uuid,
            exporter=self._exporter,
            provenance_config=LOOM_PROVENANCE_CONFIG,
        )
        package.dataset_datasetType = [_dataset_kind(dataset_type)]
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
