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
:mod:`pitloom.id_registry._types` (``id generate`` file traversal) and
:func:`pitloom.id_registry.resolve.registry_copy` (the root a wheel or sdist
reader matches members against).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable
from pathlib import Path, PurePath, PurePosixPath
from typing import TYPE_CHECKING

from pitloom.core.file_identity import file_id, stat_id
from pitloom.core.path_confine import inside_ancestor
from pitloom.core.path_probe import is_missing_errno

if TYPE_CHECKING:
    from pitloom.core.project import ProjectFile

log = logging.getLogger(__name__)

__all__ = [
    "IGNORED_DIR_NAMES",
    "PROJECT_FILES",
    "REGISTRY_IN_FILE_SET_WARNING",
    "RegistryCopy",
    "SameFile",
    "same_path",
    "warn_registry_left_out",
    "without_registry_copies",
]

#: The files that make a directory a Python project's.
PROJECT_FILES = ("pyproject.toml", "setup.cfg", "setup.py")

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

#: ``log.warning()`` format for a declared registry inside a project's file
#: set: left out of project discovery (files and Merkle root) and, as its
#: copy, of a wheel's or an sdist's members. Argument: the registry path. A
#: directory dataset has its own (``loom:``-prefixed) warning;
#: ``id generate`` leaves the registry out of its index silently.
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

    A candidate is compared by one ``stat()`` result (the caller's own when
    it has one); ``realpath`` is computed only when identity cannot decide:
    either side has none, or the two names agree. A missing target (a
    registry not created yet) is no existing file: an existing candidate
    never matches it, and two missing paths compare by ``realpath``.
    """

    __slots__ = ("_identity", "_missing", "_name", "_real")

    def __init__(self, target: Path) -> None:
        self._real = os.path.realpath(target)
        self._name = os.path.basename(self._real)
        try:
            self._identity = stat_id(os.stat(target))
            self._missing = False
        except OSError as exc:
            self._identity, self._missing = None, is_missing_errno(exc)

    def matches(
        self,
        path: str | os.PathLike[str],
        path_stat: os.stat_result | None = None,
    ) -> bool:
        """Whether *path* is the target. *path_stat* is *path*'s own
        ``os.stat()`` result, when the caller already has it."""
        if self._identity is not None or self._missing:
            identity = (
                file_id(os.fspath(path)) if path_stat is None else stat_id(path_stat)
            )
            if self._missing:
                if path_stat is not None or identity is not None:
                    return False  # an existing file is not a missing one
            elif identity == self._identity:
                return True
            # Two identities that differ: one spelling could only match if
            # the target was replaced since; that is the target's name.
            elif identity is not None and os.path.basename(path) != self._name:
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


#: How many leading parts of the registry's path a wheel member may lack:
#: the source directory of a ``src/`` layout.
_DROPPABLE_PARTS = 1
#: The fewest parts such a shortened member keeps: a package directory and
#: the file.
_MIN_SHORTENED = 2

#: How well a member matches: the parts it lacks, then whether it matched
#: only in another case. The smaller, the better.
_Rank = tuple[int, bool]


class RegistryCopy:
    """Whether an archive member path is a copy of the declared *registry*
    file, which lies below *root* (the project directory the archive was
    built from).

    The rule: the member's ``/``-separated path is the registry's path
    below *root*; or, in a wheel, that path less its first part (a
    ``src/`` layout installs ``src/demo/reg.json`` at ``demo/reg.json``),
    when at least a directory and the file remain. Never longer, never
    shorter than that: ``reg.json`` and ``data/reg.json`` are other files
    beside ``src/demo/data/reg.json``. Of the members of one archive that
    match, only the best is the copy (:meth:`pick`): the longest, then one
    spelt as the registry. Its path below *root* is taken as spelt and
    through symlinks, matching either. A part spelt in another case matches
    only where the registry's path spelt that way is the registry file (a
    case-insensitive file system). No content check: the archive carries
    the registry as it was at build time. A registry outside *root*
    matches nothing.
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
        :mod:`pitloom.core.archive_member_names`) may be a copy of the
        registry, by itself; :meth:`pick` chooses among an archive's.
        *in_sdist*: *member* is below an sdist's top directory and must be
        the registry's whole path below it."""
        return self._rank(member, in_sdist) is not None

    def pick(self, members: Iterable[str], *, in_sdist: bool = False) -> str | None:
        """The one of an archive's *members* that is the registry's copy:
        the best match (see the class), then the first in sort order;
        ``None`` when none matches."""
        ranked = [
            (rank, member)
            for member in members
            if (rank := self._rank(member, in_sdist)) is not None
        ]
        return min(ranked)[1] if ranked else None

    def _rank(self, member: str, in_sdist: bool) -> _Rank | None:
        parts = PurePosixPath(member).parts[1 if in_sdist else 0 :]
        if not parts:
            return None
        ranks = [
            rank
            for ancestor, own in self._below
            if (rank := self._at(ancestor, own, parts, in_sdist)) is not None
        ]
        return min(ranks) if ranks else None

    def _at(
        self,
        ancestor: PurePath,
        own: tuple[str, ...],
        parts: tuple[str, ...],
        whole: bool,
    ) -> _Rank | None:
        cut = len(own) - len(parts)
        if cut < 0 or cut > (0 if whole else _DROPPABLE_PARTS):
            return None
        if cut and len(parts) < _MIN_SHORTENED:
            return None
        if own[cut:] == parts:
            return cut, False
        if [p.casefold() for p in own[cut:]] == [
            p.casefold() for p in parts
        ] and self._same.matches(ancestor.joinpath(*own[:cut], *parts)):
            return cut, True
        return None


def without_registry_copies(
    files: list[ProjectFile],
    copy: RegistryCopy | None,
    *,
    in_sdist: bool = False,
    warn: Callable[[], bool] = lambda: True,
) -> list[ProjectFile]:
    """*files*, an archive's members, minus the registry's copy among them
    (:meth:`RegistryCopy.pick`; *copy* ``None`` leaves out nothing). When
    one was there, one ``WARNING:`` unless *warn* says a warning was
    already given this run."""
    if copy is None:
        return files
    chosen = copy.pick((f.distribution_path for f in files), in_sdist=in_sdist)
    if chosen is None:
        return files
    if warn():
        warn_registry_left_out(copy.path)
    return [f for f in files if f.distribution_path != chosen]
