# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Types and helper routines for Loom ID registry management.

See also: :mod:`pitloom.id_registry._registry` for ``IdRegistry`` itself,
:mod:`pitloom.id_registry._format` for the file format,
:mod:`pitloom.id_registry._harvest` for harvest and claim helpers,
:mod:`pitloom.id_registry.resolve` for registry resolution.
"""

from __future__ import annotations

import logging
import os
import stat
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from packaging.utils import canonicalize_name

from pitloom.core.file_hash import sha256_digest
from pitloom.core.path_probe import (
    UNLISTABLE_DIR_WARNING,
    UNREADABLE_FILE_WARNING,
    stat_if_present,
)
from pitloom.core.walk_rules import IGNORED_DIR_NAMES, SameFile
from pitloom.logging_config import loggable, one_line

log = logging.getLogger("pitloom.id_registry")

__all__ = [
    "AI_PACKAGE_TYPE",
    "DATASET_PACKAGE_TYPE",
    "DEFAULT_ID_REGISTRY_FILENAME",
    "FILE_TYPE",
    "PACKAGE_TYPE",
    "RegistryEntry",
    "_REGISTRY_VERSION",
    "_element_key",
    "_iter_files",
    "_require_names",
    "registry_file_error",
    "sha256_file",
    "type_id_prefix",
    "warn_unreadable_file",
]

#: What an ``id generate`` read or listing is for, in the shared ``FILE=``
#: and ``DIR=`` warnings.
_PURPOSE = "for ID registry indexing"

#: The suggested registry file name, which ``id generate`` never indexes
#: (nor the declared registry, whatever its name). There is no default
#: registry: nothing looks for this file.
DEFAULT_ID_REGISTRY_FILENAME = "loom-id-registry.json"

#: SPDX 3 compact types the registry keys elements by. A directory is a
#: ``software_File`` too (``software_fileKind == directory``).
FILE_TYPE = "software_File"
PACKAGE_TYPE = "software_Package"
AI_PACKAGE_TYPE = "ai_AIPackage"
DATASET_PACKAGE_TYPE = "dataset_DatasetPackage"

_REGISTRY_VERSION = 3


@dataclass
class RegistryEntry:
    """One registered element: its stable ``spdxId`` and, when known, the
    SHA-256 of its content (lowercase hex).

    ``sha256`` is ``None`` when there is no hash; ``""`` is never a hash
    and is rejected, so "no hash" has one spelling.
    """

    spdx_id: str
    sha256: str | None = None

    def __post_init__(self) -> None:
        if self.sha256 is not None:
            if not self.sha256:
                raise ValueError("RegistryEntry.sha256 must be None or non-empty")
            self.sha256 = self.sha256.lower()


def _element_key(*, type_name: str, name: str) -> tuple[str, str]:
    """Return the registry key ``(type_name, name)`` for an element.

    The one place a :data:`PACKAGE_TYPE` name is PEP 503 canonicalised
    (:func:`packaging.utils.canonicalize_name`), so a declared ``"PyYAML"``
    and a looked-up ``"pyyaml"`` hit one entry. Every other type keeps
    its name verbatim. Keyword-only: both arguments are ``str``, so a
    swapped positional call would still type-check.
    """
    if type_name == PACKAGE_TYPE:
        return (type_name, canonicalize_name(name))
    return (type_name, name)


def _require_names(names: Sequence[str]) -> None:
    """Raise ``TypeError`` when *names* is one ``str``: a ``str`` is a
    ``Sequence[str]`` too, and would be tried character by character."""
    if isinstance(names, str):
        raise TypeError("names must be a sequence of names, not one str")


def registry_file_error(path: Path, reason: str) -> ValueError:
    """Build the one ``ValueError`` shape every registry file failure
    raises: ``ID registry file {path}: {reason}``.

    A single helper so every failure reason (not found, unreadable, bad
    JSON, wrong shape, wrong version, malformed entry, duplicate, a
    project root that cannot be stored) shares identical wording up to
    its *reason* -- the CLI, the library API and the Hatchling hook all
    surface this message verbatim.
    """
    return ValueError(f"ID registry file {path}: {reason}")


def sha256_file(path: Path) -> str:
    """Return the hex-encoded SHA-256 digest of *path*'s contents, streamed
    by the shared reader (:func:`~pitloom.core.file_hash.sha256_digest`),
    never read whole."""
    return sha256_digest(path).hex()


def type_id_prefix(type_name: str) -> str:
    """Return the spdxId fragment prefix for a compact type name: the part
    after the first ``_`` (``software_File`` -> ``File``), else the name."""
    _, _, rest = type_name.partition("_")
    return rest or type_name


def _relative_parts(file_path: Path, root: Path, project_root: Path) -> tuple[str, ...]:
    """*file_path*'s directory parts below *project_root*, else below the
    walk *root* (a path outside the project).

    Never the absolute parts: a project under ``/x/build/`` must not be
    skipped because of a directory above it.
    """
    try:
        return file_path.relative_to(project_root).parts[:-1]
    except ValueError:
        return file_path.relative_to(root).parts[:-1]


def _is_eligible_file(
    file_path: Path,
    seen: set[Path],
    relative_dirs: tuple[str, ...],
    exclude: SameFile | None,
) -> bool:
    """Check if a path is an eligible, unvisited file for registry indexing.

    *relative_dirs* are its parent directory names below the project;
    *exclude* matches the declared registry file, which is never indexed.
    A ``stat()`` failure other than absence raises (see
    :func:`~pitloom.core.path_probe.stat_if_present`).
    """
    if any(part in IGNORED_DIR_NAMES for part in relative_dirs):
        return False
    if file_path.name == DEFAULT_ID_REGISTRY_FILENAME or file_path in seen:
        return False
    file_stat = stat_if_present(file_path)
    if file_stat is None or not stat.S_ISREG(file_stat.st_mode):
        return False
    return exclude is None or not exclude.matches(file_path, file_stat)


def _shown(path: str | os.PathLike[str], project_root: Path) -> str:
    """*path* as the ``FILE=``/``DIR=`` warnings show it: relative to
    *project_root* in POSIX form, as ``pitloom project`` shows it, else as
    given (a path outside the project)."""
    try:
        return Path(path).relative_to(project_root).as_posix()
    except ValueError:
        return os.fspath(path)


def warn_unreadable_file(path: Path, project_root: Path, error: OSError) -> None:
    """Log the shared ``FILE=`` warning for *path*, which ``id generate``
    could not read and leaves out of the index."""
    log.warning(
        UNREADABLE_FILE_WARNING,
        loggable(_shown(path, project_root)),
        _PURPOSE,
        one_line(error),
    )


def _walk_files(root: Path, project_root: Path) -> list[Path]:
    """Every file name below the directory *root*, sorted as ``Path``s; a
    directory named in :data:`~pitloom.core.walk_rules.IGNORED_DIR_NAMES`
    is pruned, a symlink to a directory is not followed, and one that
    cannot be listed gets the shared ``DIR=`` warning."""

    def _warn_unlistable(error: OSError) -> None:
        log.warning(
            UNLISTABLE_DIR_WARNING,
            loggable(_shown(error.filename, project_root)),
            _PURPOSE,
            one_line(error),
        )

    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=_warn_unlistable):
        dirnames[:] = [name for name in dirnames if name not in IGNORED_DIR_NAMES]
        found.extend(Path(dirpath, name) for name in filenames)
    found.sort()
    return found


def _iter_files(
    paths: list[Path], project_root: Path, exclude: Path | None = None
) -> Iterator[Path]:
    """Yield every regular file under *paths* in deterministic order,
    except the *exclude* file (the declared registry).

    A missing path is skipped with a warning; one that cannot be
    ``stat()``-ed raises, on every Python version. Below a directory path,
    a file that cannot be ``stat()``-ed (its directory not searchable) is
    skipped with the shared ``FILE=`` warning, a directory that cannot be
    listed with the ``DIR=`` one, as ``pitloom project`` does."""
    seen: set[Path] = set()
    excluded = None if exclude is None else SameFile(exclude)

    for raw_path in paths:
        root = raw_path if raw_path.is_absolute() else project_root / raw_path
        root_stat = stat_if_present(root)
        if root_stat is None:
            log.warning("ID registry: path not found, skipping: %s", root)
            continue

        if not stat.S_ISDIR(root_stat.st_mode):
            candidates = [root]
        else:
            candidates = _walk_files(root, project_root)
        for file_path in candidates:
            relative_dirs = _relative_parts(file_path, root, project_root)
            try:
                eligible = _is_eligible_file(file_path, seen, relative_dirs, excluded)
            except OSError as exc:
                warn_unreadable_file(file_path, project_root, exc)
                continue
            if eligible:
                seen.add(file_path)
                yield file_path
