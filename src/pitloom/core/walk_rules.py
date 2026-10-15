# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Rules shared by every project file walk.

One definition of the directory names a walk skips, of "is this the same
file" for the declared Loom ID registry, of "is this archive member a copy
of it", and of the warning given when that registry sits inside the walked
tree.

See also: :mod:`pitloom.core._models_wheel` (project file discovery),
:mod:`pitloom.id_registry._types` (``id generate`` indexing) and
:func:`pitloom.id_registry.resolve.registry_copy` (the root a wheel or sdist
reader matches members against).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path, PurePath, PurePosixPath
from typing import TYPE_CHECKING

from pitloom.core.file_identity import file_id, stat_id
from pitloom.core.path_confine import inside_ancestor

if TYPE_CHECKING:
    from pitloom.core.project import ProjectFile

log = logging.getLogger(__name__)

__all__ = [
    "IGNORED_DIR_NAMES",
    "REGISTRY_IN_FILE_SET_WARNING",
    "RegistryCopy",
    "SameFile",
    "same_path",
    "warn_registry_left_out",
    "without_registry_copies",
]

#: Directory names every walk prunes (``id generate``, a directory
#: dataset), matched against the path parts below the walk's base only:
#: the project for ``id generate`` (the walk root for a path outside it),
#: the dataset directory for a dataset. Never the parts above it, so a
#: project under ``/x/build/`` is still walked.
IGNORED_DIR_NAMES = frozenset(
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

#: ``log.warning()`` format for a declared registry inside the file set.
#: Argument: the registry path. True for every walk: a wheel's files and
#: Merkle root, ``embed-wheel`` (no root), a dataset, ``id generate``.
REGISTRY_IN_FILE_SET_WARNING = (
    "ID registry: %s is inside the project's file set; left out of it"
)


# pylint: disable-next=too-few-public-methods
class SameFile:
    """Whether a path names one *target* file, the target resolved once.

    The rule: the same ``(st_dev, st_ino)``
    (:func:`~pitloom.core.file_identity.file_id`; ``st_ino == 0`` on
    FAT/exFAT is no identity), else the same ``os.path.realpath``. Never
    ``Path ==``: that is case-insensitive on Windows and not on Linux, and
    one side may be lexical (a CLI registry path) while the other is
    resolved (macOS ``/tmp`` is ``/private/tmp``). Identity also catches
    a case-insensitive file system spelling one file in two cases.

    A candidate is compared by one ``stat()`` result, the caller's own when
    it has one; only a candidate with no identity, or named as the target
    is, pays for a ``realpath``.
    """

    __slots__ = ("_identity", "_name", "_real")

    def __init__(self, target: Path) -> None:
        self._real = os.path.realpath(target)
        self._name = os.path.basename(self._real)
        self._identity = file_id(target)

    def matches(
        self,
        path: str | os.PathLike[str],
        path_stat: os.stat_result | None = None,
    ) -> bool:
        """Whether *path* is the target. *path_stat* is *path*'s own
        ``os.stat()`` result, when the caller already has it."""
        if self._identity is not None:
            identity = (
                file_id(os.fspath(path)) if path_stat is None else stat_id(path_stat)
            )
            if identity == self._identity:
                return True
            # Two identities that differ: one spelling could only match if
            # the target was replaced since; that is the target's name.
            if identity is not None and os.path.basename(path) != self._name:
                return False
        return os.path.realpath(path) == self._real


def same_path(first: Path, second: Path) -> bool:
    """True when *first* and *second* name the same file, by
    :class:`SameFile`'s rule. Neither has to exist: two missing paths
    compare by ``realpath``."""
    return SameFile(second).matches(first)


def warn_registry_left_out(registry_path: Path) -> None:
    """Warn that the declared registry was inside the walked file set and
    is left out of it."""
    log.warning(REGISTRY_IN_FILE_SET_WARNING, registry_path)


# pylint: disable-next=too-few-public-methods
class RegistryCopy:
    """Whether an archive member path is a copy of the declared *registry*
    file, which lies below *root* (the project directory the archive was
    built from).

    The rule: the member's ``/``-separated path is the registry's path
    below *root*, or a tail of it (a wheel from a ``src/`` layout drops the
    leading parts); never longer, and never another file's tail. Its path
    below *root* is taken as spelt and through symlinks, matching either.
    A part spelt in another case matches only where the registry's path
    spelt that way is the registry file (a case-insensitive file system).
    No content check: a built archive carries the registry as it was at
    build time, rewritten since. A registry outside *root* matches nothing.
    """

    __slots__ = ("_below", "_same", "path")

    def __init__(self, registry: Path, root: Path) -> None:
        self.path = registry
        self._same = SameFile(registry)
        real_root = PurePath(os.path.realpath(root))
        below: list[tuple[PurePath, tuple[str, ...]]] = []
        for spelling in map(
            PurePath, (os.path.abspath(registry), os.path.realpath(registry))
        ):
            ancestor = inside_ancestor(spelling, real_root)
            if ancestor is None:
                continue
            parts = spelling.relative_to(ancestor).parts
            if parts and (ancestor, parts) not in below:
                below.append((ancestor, parts))
        self._below = tuple(below)

    def matches(self, member: str, *, in_sdist: bool = False) -> bool:
        """Whether archive member *member* (an install-location name, see
        :mod:`pitloom.core.archive_member_names`) is a copy of the registry.
        *in_sdist*: *member* is below an sdist's top directory and must be
        the registry's whole path below it, not a tail."""
        parts = PurePosixPath(member).parts[1 if in_sdist else 0 :]
        return bool(parts) and any(
            self._at(ancestor, own, parts, in_sdist) for ancestor, own in self._below
        )

    def _at(
        self,
        ancestor: PurePath,
        own: tuple[str, ...],
        parts: tuple[str, ...],
        whole: bool,
    ) -> bool:
        cut = len(own) - len(parts)
        if cut < 0 or (whole and cut):
            return False
        if own[cut:] == parts:
            return True
        return [p.casefold() for p in own[cut:]] == [
            p.casefold() for p in parts
        ] and self._same.matches(ancestor.joinpath(*own[:cut], *parts))


def without_registry_copies(
    files: list[ProjectFile],
    copy: RegistryCopy | None,
    *,
    in_sdist: bool = False,
    warn: Callable[[], bool] = lambda: True,
) -> list[ProjectFile]:
    """*files*, an archive's members, minus each copy of the declared
    registry (:meth:`RegistryCopy.matches`; *copy* ``None`` leaves out
    nothing). When one was there, one ``WARNING:`` unless *warn* says a
    warning was already given this run."""
    if copy is None:
        return files
    kept = [
        f for f in files if not copy.matches(f.distribution_path, in_sdist=in_sdist)
    ]
    if len(kept) != len(files) and warn():
        warn_registry_left_out(copy.path)
    return kept
