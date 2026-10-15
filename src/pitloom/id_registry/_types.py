# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Types and helper routines for Loom ID registry management.

See also: :mod:`pitloom.id_registry._registry` for ``IdRegistry`` itself,
:mod:`pitloom.id_registry._format` for the file format,
:mod:`pitloom.id_registry._generate` for the indexing that uses the file
traversal here, :mod:`pitloom.id_registry._harvest` for harvest helpers,
:mod:`pitloom.id_registry._session` for claims,
:mod:`pitloom.id_registry.resolve` for registry resolution.
"""

from __future__ import annotations

import logging
import os
import stat
from collections.abc import Iterable, Iterator, Sequence
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
    "_unstorable_name_error",
    "is_utf8_text",
    "registry_file_error",
    "sha256_file",
    "type_id_prefix",
    "unencodable_message",
    "warn_unreadable_file",
]

#: What an ``id generate`` read or listing is for, in the shared ``FILE=``
#: and ``DIR=`` warnings.
_PURPOSE = "for ID registry indexing"

#: The suggested registry file name. There is no default registry: nothing
#: looks for this file, and ``id generate`` leaves out only the declared
#: registry (by identity, whatever its name).
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


def _is_eligible_file(
    file_path: Path,
    seen: set[Path],
    exclude: SameFile | None,
) -> bool:
    """Check if a path is an eligible, unvisited file for registry indexing.

    Ignored directories never reach it (the walk prunes them and a PATH
    naming one is skipped up front). *exclude* matches the declared
    registry file, which is never indexed.
    A ``stat()`` failure other than absence raises (see
    :func:`~pitloom.core.path_probe.stat_if_present`).
    """
    if file_path in seen:
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


def warn_unreadable_file(
    path: Path, project_root: Path, error: OSError | ValueError
) -> None:
    """Log the shared ``FILE=`` warning for *path*, which ``id generate``
    could not read (or whose name a registry cannot hold) and leaves out
    of the index."""
    log.warning(
        UNREADABLE_FILE_WARNING,
        loggable(_shown(path, project_root)),
        _PURPOSE,
        one_line(error),
    )


def _walk_files(root: Path, project_root: Path, strict: bool = True) -> list[Path]:
    """Every file name below the directory *root*, sorted as ``Path``s; a
    directory named in :data:`~pitloom.core.walk_rules.IGNORED_DIR_NAMES`
    is pruned, a symlink to a directory is not followed, and one that
    cannot be listed gets the shared ``DIR=`` warning. *root* itself
    failing to list raises when *strict*, else gets that warning too."""

    def _warn_unlistable(error: OSError) -> None:
        if strict and error.filename == os.fspath(root):
            raise error
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


#: Why a registry cannot hold a name, in every message about one.
UNENCODABLE_REASON = "cannot be encoded as UTF-8 (lone surrogate)"


def is_utf8_text(text: str) -> bool:
    """Whether *text* encodes as UTF-8: not when it holds a lone surrogate
    (a non-UTF-8 file name read by ``surrogateescape``, or a JSON ``\\ud800``
    escape), which the canonical-JSON save cannot write."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def unencodable_message(what: str, text: str) -> str:
    """The one wording for *text* the registry cannot hold, shown escaped
    (a lone surrogate would crash the log handler); *what* names it."""
    return f"ID registry: {what} {ascii(text)} {UNENCODABLE_REASON}"


def _unstorable_name_error(path: Path, project_root: Path) -> ValueError | None:
    """The error for a *path* whose registry name is not UTF-8 encodable (a
    surrogate-escaped OS file name), else ``None``: a registry file is
    UTF-8 JSON and cannot hold it."""
    if is_utf8_text(_shown(path, project_root)):
        return None
    return ValueError(f"name {UNENCODABLE_REASON}")


def _skipped_name_in(root: Path, project_root: Path, is_dir: bool) -> str | None:
    """The first ignored directory name in an explicit PATH *root* below the
    project (its own name too when a directory), else ``None``; such a path
    indexes nothing."""
    try:
        parts = root.relative_to(project_root).parts
    except ValueError:
        return None
    return next(
        (part for part in parts[: None if is_dir else -1] if part in IGNORED_DIR_NAMES),
        None,
    )


def _root_files(root: Path, project_root: Path, strict: bool) -> Iterable[Path]:
    """The files the PATH *root* names (see :func:`_root_candidates`); a
    read or listing failure of *root* itself raises."""
    root_stat = stat_if_present(root)
    if root_stat is None:
        log.warning("ID registry: path not found, skipping: %s", root)
        return ()

    is_dir = stat.S_ISDIR(root_stat.st_mode)
    skipped = _skipped_name_in(root, project_root, is_dir)
    if skipped is not None:
        log.warning(
            "ID registry: path has a skipped directory name (%s), skipping: %s",
            skipped,
            root,
        )
        return ()
    if is_dir:
        return _walk_files(root, project_root, strict)
    if stat.S_ISREG(root_stat.st_mode):
        with open(root, "rb"):  # a read failure raises
            pass
    return [root]


def _root_candidates(
    raw_path: Path, project_root: Path, explicit: bool
) -> Iterable[Path]:
    """The files a PATH names: itself, or the walk below a directory; empty,
    with a warning, when it is missing or has an ignored directory name
    below the project.

    A PATH that cannot be read or listed is a ``ValueError`` naming it
    when *explicit* (given by the user); an implicit default root gets the
    shared ``FILE=`` / ``DIR=`` warning and is left out."""
    root = raw_path if raw_path.is_absolute() else project_root / raw_path
    try:
        return _root_files(root, project_root, explicit)
    except OSError as exc:
        if explicit:
            raise ValueError(
                f"PATH {loggable(_shown(root, project_root))}: could not be "
                f"read: {one_line(exc.strerror or exc)}"
            ) from exc
        warn_unreadable_file(root, project_root, exc)
        return ()


def _eligible_files(
    candidates: Iterable[Path],
    project_root: Path,
    seen: set[Path],
    excluded: SameFile | None,
) -> Iterator[Path]:
    """Yield the *candidates* that are storable, readable, new and not the
    *excluded* file, warning about each one that is not; record them in *seen*."""
    for file_path in candidates:
        name_error = _unstorable_name_error(file_path, project_root)
        if name_error is not None:
            warn_unreadable_file(file_path, project_root, name_error)
            continue
        try:
            eligible = _is_eligible_file(file_path, seen, excluded)
        except OSError as exc:
            warn_unreadable_file(file_path, project_root, exc)
            continue
        if eligible:
            seen.add(file_path)
            yield file_path


def _iter_files(
    paths: list[Path],
    project_root: Path,
    exclude: Path | None = None,
    *,
    explicit: bool = True,
) -> Iterator[Path]:
    """Yield every regular file under *paths* in deterministic order,
    except the *exclude* file (the declared registry, matched by identity).

    A missing path, or one with an ignored directory name below the
    project, is skipped with a warning. One that cannot be ``stat()``-ed
    or read (a directory: listed) raises a ``ValueError`` naming it, on
    every Python version, unless *explicit* is false (an implicit default
    root: a ``FILE=``/``DIR=`` warning instead). Below a directory path,
    a file that cannot be ``stat()``-ed is skipped with the shared
    ``FILE=`` warning, a directory that cannot be listed with the
    ``DIR=`` one, as ``pitloom project`` does."""
    seen: set[Path] = set()
    excluded = None if exclude is None else SameFile(exclude)
    for raw_path in paths:
        yield from _eligible_files(
            _root_candidates(raw_path, project_root, explicit),
            project_root,
            seen,
            excluded,
        )
