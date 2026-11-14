# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The key and SHA-256 ``loom id generate -e NAME:TYPE`` stores.

See also: :mod:`pitloom.cli.id` (the command), :mod:`pitloom._loom_dataset`
(the loom lookup of a dataset pin).
"""

from __future__ import annotations

import logging
from pathlib import Path

from pitloom._loom_dataset import dataset_digest
from pitloom.core import dataset_hash
from pitloom.core.path_probe import is_regular_file
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    PACKAGE_TYPE,
    IdRegistry,
    artifact_key,
    package_key,
    sha256_file,
    split_package_key,
)
from pitloom.id_registry.import_keys import name_key_reason
from pitloom.logging_config import loggable
from pitloom.messages import emit
from pitloom.messages.id_registry_ids import (
    ENTITY_BY_NAME_LINE,
    KEY_MODEL_PIN,
    KEY_NOT_A_FILE,
    NO_VERSION_LINE,
    PIN_WITHOUT_HASH_LINE,
    REGISTRY_HASH_MISSING,
    REGISTRY_IDENTITY_MISSING,
    REGISTRY_PATH_KEY_UNUSABLE,
)

log = logging.getLogger("pitloom.id_registry")

__all__ = [
    "ENTITY_STORED_AS_INFO",
    "entity_entry",
]

#: ``log.info()`` format, once per ``-e``: NAME stored under another
#: spelling of its path or package key (arguments: NAME, the key).
ENTITY_STORED_AS_INFO = "ID registry: -e %s stored as %s"


# pylint: disable-next=too-few-public-methods
class _Held(logging.Filter):
    """Holds, instead of passing on, what one logger logs."""

    def __init__(self) -> None:
        super().__init__()
        self.held: list[logging.LogRecord] = []

    def filter(self, record: logging.LogRecord) -> bool:
        self.held.append(record)
        return False


def _pin_digest(
    registry: IdRegistry, path: Path, max_bytes: int
) -> tuple[str | None, str]:
    """The digest a loom package of the dataset at *path* carries
    (:func:`~pitloom._loom_dataset.dataset_digest`, reading at most
    *max_bytes*) and ``""``; or ``None``
    and why: what hashing logged (over the ceiling, unreadable), taken
    instead of logged, else ``nothing to hash`` (an empty directory). With
    a digest, whatever hashing logged is passed on unchanged."""
    hold = _Held()
    hash_log = logging.getLogger(dataset_hash.__name__)
    hash_log.addFilter(hold)
    try:
        found = dataset_digest(registry, path, max_bytes=max_bytes)
    finally:
        hash_log.removeFilter(hold)
    if found.hex_digest is not None:
        for record in hold.held:
            hash_log.handle(record)
        return found.hex_digest, ""
    reasons = "; ".join(record.getMessage() for record in hold.held)
    return None, reasons or "nothing to hash"


def _info_stored_as(name: str, key: str) -> None:
    """The one :data:`ENTITY_STORED_AS_INFO` for ``-e`` NAME stored under
    *key*; nothing when *key* is NAME as typed."""
    if key != name:
        log.info(ENTITY_STORED_AS_INFO, loggable(name), loggable(key))


def _package_entry(name: str) -> str:
    """A package's key: :func:`~pitloom.id_registry.package_key` of what NAME
    states (``NAME@VERSION``, split at its first ``@``). With no version it
    holds only a package that states none, one
    ``registry-identity-missing`` ``INFO:``; else, spelt otherwise than NAME, one
    :data:`ENTITY_STORED_AS_INFO`."""
    stated, version = split_package_key(name)
    key = package_key(stated, version)
    if "@" not in key:  # a name's own "@" is "%40": the "@" is the version's
        emit(
            log,
            REGISTRY_IDENTITY_MISSING,
            logging.INFO,
            line=NO_VERSION_LINE,
            entity=name,
        )
    else:
        _info_stored_as(name, key)
    return key


def _dataset_entry(
    registry: IdRegistry, path: Path, name: str, max_bytes: int
) -> tuple[str, str | None]:
    """A dataset's key and digest: its path key and the digest its loom
    package carries (hashing at most *max_bytes*) when it exists below the
    root; else *name* and none,
    with one ``registry-hash-missing`` ``INFO:``."""
    key = artifact_key(registry, path=path, name=name)
    if not key.path:
        _info_pin_without_hash(name, name_key_reason(path))
        return name, None
    _info_stored_as(name, key.key)
    digest, reason = _pin_digest(registry, path, max_bytes)
    if digest is None:
        _info_pin_without_hash(key.key, reason)
    return key.key, digest


def _info_pin_without_hash(key: str, why: str) -> None:
    """The one ``INFO:`` for a dataset pin *key* stored with no SHA-256,
    *why* saying why."""
    emit(
        log,
        REGISTRY_HASH_MISSING,
        logging.INFO,
        line=PIN_WITHOUT_HASH_LINE,
        entity=key,
        why=why,
    )


def _file_entry(
    registry: IdRegistry, path: Path, type_name: str, name: str
) -> tuple[str, str | None]:
    """A model's or a file's key and SHA-256: its path key and the file's
    SHA-256 (streamed) when it is a regular file below the root, as every
    lookup of it is; else *name* and none, with one
    ``registry-path-key-unusable`` ``INFO:``."""
    key = artifact_key(registry, path=path, name=name)
    if key.path and is_regular_file(path):
        _info_stored_as(name, key.key)
        return key.key, sha256_file(path)
    if type_name == AI_PACKAGE_TYPE:
        reason = KEY_MODEL_PIN
    else:
        reason = KEY_NOT_A_FILE if key.path else name_key_reason(path)
    emit(
        log,
        REGISTRY_PATH_KEY_UNUSABLE,
        logging.INFO,
        line=ENTITY_BY_NAME_LINE,
        entity=name,
        key_reason=reason,
    )
    return name, None


def entity_entry(
    registry: IdRegistry,
    project_dir: Path,
    type_name: str,
    name: str,
    max_dataset_hash_bytes: int,
) -> tuple[str, str | None]:
    """The key and SHA-256 ``-e NAME:TYPE`` is stored under, NAME taken
    from *project_dir*: a dataset by :func:`_dataset_entry` (hashing at most
    *max_dataset_hash_bytes*), a model or a
    file by :func:`_file_entry` (both content-gated when keyed by path), a
    package by :func:`_package_entry` (``NAME@VERSION``, no hash); any
    other type NAME as given and no hash."""
    if type_name == PACKAGE_TYPE:
        return _package_entry(name), None
    path = project_dir / name
    if type_name == DATASET_PACKAGE_TYPE:
        return _dataset_entry(registry, path, name, max_dataset_hash_bytes)
    if type_name in (AI_PACKAGE_TYPE, FILE_TYPE):
        return _file_entry(registry, path, type_name, name)
    return name, None
