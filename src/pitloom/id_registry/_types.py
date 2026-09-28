# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Types and helper routines for Loom ID registry management.

See also: :mod:`pitloom.id_registry._registry` for ``IdRegistry`` itself,
:mod:`pitloom.id_registry._harvest` for harvest and claim helpers,
:mod:`pitloom.id_registry.resolve` for registry resolution.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.utils import canonicalize_name
from spdx_python_model.bindings import v3_0_1 as spdx3

log = logging.getLogger("pitloom.id_registry")

__all__ = [
    "DEFAULT_ID_REGISTRY_FILENAME",
    "DIRECTORY_ENTITY_TYPE",
    "EntityEntry",
    "FileEntry",
    "PACKAGE_ENTITY_TYPE",
    "_IGNORED_DIR_NAMES",
    "_REGISTRY_VERSION",
    "_entity_key",
    "_iter_files",
    "_sha256_from_verified_using",
    "_type_id_prefix",
    "sha256_file",
]

DEFAULT_ID_REGISTRY_FILENAME = "loom-id-registry.json"

#: The SPDX 3 compact type a directory is registered under (an
#: :class:`~spdx_python_model.bindings.v3_0_1.software_File` with
#: ``software_fileKind == directory`` -- there is no dedicated "directory"
#: SHACL type, so it shares ``software_File``'s compact type with a regular
#: file entry). Shared constant so a directory lookup/harvest never drifts
#: from a hand-typed literal.
DIRECTORY_ENTITY_TYPE = "software_File"

#: The SPDX 3 compact type a deployed dependency package (and a project's
#: own main package) is registered under -- shared by
#: :func:`~pitloom.assemble.spdx3._document_deployed._build_deployed_package`'s
#: lookup and :func:`_entity_key`'s canonicalization (see its docstring).
PACKAGE_ENTITY_TYPE = "software_Package"

_IGNORED_DIR_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".pyrefly_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        ".tox",
        ".hatch",
        "fragments",
    }
)

_REGISTRY_VERSION = 2


@dataclass
class FileEntry:
    """A single registered file: its stable ``spdxId`` and content hash."""

    spdx_id: str
    sha256: str

    def __post_init__(self) -> None:
        self.sha256 = self.sha256.lower()


@dataclass
class EntityEntry:
    """A single registered named entity (e.g. an AI model) and its ``spdxId``.

    No ``type`` field: :class:`~pitloom.id_registry.IdRegistry` keys its
    ``entities`` dict by ``(type, name)``, so the type already lives in the
    key -- storing it again here would be the same fact in two places, free
    to drift out of sync on a hand-edited registry file.
    """

    spdx_id: str


def _entity_key(name: str, type_name: str) -> tuple[str, str]:
    """Return the ``entities`` dict key for a named entity of *type_name*.

    The single place a :data:`PACKAGE_ENTITY_TYPE` entity's name is PEP 503
    canonicalized (:func:`packaging.utils.canonicalize_name`) -- every
    reader/writer of :attr:`~pitloom.id_registry.IdRegistry.entities` for
    that type (:meth:`~pitloom.id_registry.IdRegistry.register_entity`,
    :meth:`~pitloom.id_registry.IdRegistry.lookup_entity`, harvest via
    :func:`~pitloom.id_registry._harvest._import_sbom_element`) goes
    through this, so a package's declared name (e.g. ``"PyYAML"``) and a
    lowercased lookup key (e.g. ``"pyyaml"``, from pipdeptree) always
    resolve to the identical entry. Every other entity type is keyed by
    its name verbatim.
    """
    if type_name == PACKAGE_ENTITY_TYPE:
        return (type_name, canonicalize_name(name))
    return (type_name, name)


def sha256_file(path: Path) -> str:
    """Return the hex-encoded SHA-256 digest of *path*'s contents.

    Streams the file in chunks (never ``read_bytes()``/``Path.read_text()``
    the whole thing into memory at once) -- narrow public helper so
    sibling modules needing a file's SHA-256 (:mod:`pitloom.id_registry`,
    :mod:`pitloom._loom_caller`) share one implementation instead of each
    writing its own chunked-read loop.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _type_id_prefix(type_name: str) -> str:
    """Return the SPDX ID fragment prefix for a SHACL type name."""
    _, _, rest = type_name.partition("_")
    return rest or type_name


def _sha256_from_verified_using(obj: Any) -> str | None:
    """Return the SHA-256 hex digest from *obj*'s ``verifiedUsing`` list."""
    for h in getattr(obj, "verifiedUsing", None) or []:
        if getattr(h, "algorithm", None) == spdx3.HashAlgorithm.sha256:
            value = getattr(h, "hashValue", None)
            if value:
                return str(value)
    return None


def _is_eligible_file(file_path: Path, seen: set[Path]) -> bool:
    """Check if a path is an eligible, unvisited file for registry indexing."""
    if not file_path.is_file():
        return False
    if any(part in _IGNORED_DIR_NAMES for part in file_path.parts):
        return False
    if file_path.name == DEFAULT_ID_REGISTRY_FILENAME:
        return False
    if file_path in seen:
        return False
    return True


def _iter_files(paths: list[Path], project_root: Path) -> Iterator[Path]:
    """Yield every regular file under *paths* in deterministic order."""
    seen: set[Path] = set()

    for raw_path in paths:
        root = raw_path if raw_path.is_absolute() else project_root / raw_path
        if not root.exists():
            log.warning("ID registry: path not found, skipping: %s", root)
            continue

        candidates: Iterable[Path] = (
            [root] if root.is_file() else sorted(root.rglob("*"))
        )
        for file_path in candidates:
            if _is_eligible_file(file_path, seen):
                seen.add(file_path)
                yield file_path
