# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Types and helper routines for Loom ID registry management.

See also: :mod:`pitloom.ids` for IdRegistry and registry resolution.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

log = logging.getLogger(__name__)

DEFAULT_REGISTRY_FILENAME = "loom-ids.json"

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

_REGISTRY_VERSION = 1
_DEFAULT_IDS_GENERATE_DIR_NAMES: tuple[str, ...] = ("src", "data", "models")


@dataclass
class FileEntry:
    """A single registered file: its stable ``spdxId`` and content hash."""

    spdx_id: str
    sha256: str

    def __post_init__(self) -> None:
        self.sha256 = self.sha256.lower()


@dataclass
class EntityEntry:
    """A single registered named entity (e.g. an AI model) and its ``spdxId``."""

    type: str
    spdx_id: str


def _sha256_file(path: Path) -> str:
    """Return the hex-encoded SHA-256 digest of *path*'s contents."""
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
    if file_path.name == DEFAULT_REGISTRY_FILENAME:
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
            log.warning("Registry: path not found, skipping: %s", root)
            continue

        candidates: Iterable[Path] = (
            [root] if root.is_file() else sorted(root.rglob("*"))
        )
        for file_path in candidates:
            if _is_eligible_file(file_path, seen):
                seen.add(file_path)
                yield file_path
