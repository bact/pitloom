# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which release and which file of it to read: pure functions over the PyPI
JSON API answer, no I/O.

See also: :mod:`pitloom.extract.remote.pypi` (which fetches the answer, says
each decision and downloads the pick).

The answer is untrusted: every value used is type-checked, and a file name
must be a bare base name that :mod:`packaging.utils` parses, of the project
and release asked for, before it is a candidate. Every pick is a total
order, so the order of the answer never changes it.

- Release (no version given): stable and not yanked first, then a
  pre-release not yanked, then a yanked one; the newest by PEP 440 within
  that, a tie broken on the version text. A release counts when it has a
  wheel or sdist with a SHA-256 digest; it is yanked when every such file is.
- Wheel: the best rank of its tags in the running environment's tag order
  (:func:`packaging.tags.sys_tags`, the order pip uses); a file not yanked
  before a yanked one, then the rank, then the file name.
- Sdist: not yanked first, then ``.tar.gz`` before ``.zip``, then the name.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from packaging.tags import Tag, sys_tags
from packaging.utils import (
    parse_sdist_filename,
    parse_wheel_filename,
)
from packaging.version import InvalidVersion, Version

from pitloom.core.pep440 import parse_version
from pitloom.core.untrusted_text import DISPLAY_CONTROLS

__all__ = [
    "PRERELEASE",
    "SDIST",
    "STABLE",
    "WHEEL",
    "YANKED",
    "ReleaseChoice",
    "ReleaseFile",
    "SdistPick",
    "WheelPick",
    "file_name_problem",
    "pick_sdist",
    "pick_wheel",
    "read_files",
    "select_release",
    "versions_equal_to",
]

#: A wheel.
WHEEL: Final = "wheel"
#: An sdist.
SDIST: Final = "sdist"

#: The kinds of release :func:`select_release` tells apart, best first.
STABLE: Final = "stable"
PRERELEASE: Final = "prerelease"
YANKED: Final = "yanked"

#: The JSON ``packagetype`` of each kind.
_PACKAGE_TYPES: Final = {"bdist_wheel": WHEEL, "sdist": SDIST}

#: The longest file name read (most file systems' limit).
_MAX_NAME: Final = 255

#: A SHA-256 in hex, either case.
_SHA256_RE: Final = re.compile(r"[0-9a-fA-F]{64}")

#: Characters no file name of a release holds: a path separator, a
#: character Windows refuses in a name, a quote.
_BAD_CHARS: Final = frozenset('/\\:<>"|?*\x00')

#: The device names Windows reserves, whatever follows the first ``.``
#: (``nul.x-1.0.tar.gz`` opens the device): the stem, case-folded, white
#: space at its end stripped. ``COM`` and ``LPT`` take a digit or a
#: superscript one, two or three.
_DEVICE_NAMES: Final = frozenset(
    {"con", "prn", "aux", "nul", "conin$", "conout$"}
    | {
        f"{port}{number}"
        for port in ("com", "lpt")
        for number in (*"0123456789", "\u00b9", "\u00b2", "\u00b3")
    }
)

#: Why a file name the answer lists twice is refused.
_TWICE: Final = "the answer lists the file name more than once"


@dataclass(frozen=True)
class ReleaseFile:
    """A file of a release, as the answer lists it, checked."""

    filename: str
    kind: str
    url: str
    #: The SHA-256 the answer declares, lower-case hex; ``None`` when it
    #: declares none, or one that is not 64 hex digits.
    sha256: str | None
    yanked: bool
    yanked_reason: str | None
    #: The wheel's tags (none for an sdist).
    tags: frozenset[Tag] = frozenset()


@dataclass(frozen=True)
class WheelPick:
    """The wheel picked, and how many wheels matched the environment."""

    file: ReleaseFile
    compatible: int


@dataclass(frozen=True)
class SdistPick:
    """The sdist picked, and how many sdists the release has."""

    file: ReleaseFile
    count: int


@dataclass(frozen=True)
class ReleaseChoice:
    """The release picked when no version is given: its version as the
    answer lists it, and :data:`STABLE`, :data:`PRERELEASE` or
    :data:`YANKED`."""

    version: str
    kind: str


def _environment_tags() -> list[Tag]:
    """The running interpreter's and platform's tags, best first (a test
    patches this, not the host)."""
    return list(sys_tags())


def file_name_problem(filename: str) -> str | None:
    """Why *filename*, from the answer, cannot be a file name of a release
    (a path, a control character, a name Windows refuses), or ``None``."""
    if not filename or len(filename) > _MAX_NAME:
        return "the file name is empty or too long"
    if (
        not filename.isprintable()
        or not DISPLAY_CONTROLS.isdisjoint(filename)
        or not _BAD_CHARS.isdisjoint(filename)
    ):
        return "the file name holds a path separator or a control character"
    if not filename.isascii():
        # Every valid wheel and sdist name is ASCII; IGNORECASE matching
        # elsewhere would read U+212A (Kelvin) as ``k``.
        return "the file name is not ASCII"
    if filename.startswith(".") or ".." in filename or filename[-1] in ". ":
        return "the file name is not a plain file name"
    if filename.partition(".")[0].casefold().rstrip(" ") in _DEVICE_NAMES:
        return "the file name is a device name on Windows"
    return None


def _wheel_mismatch(filename: str, canonical: str, version: Version) -> str | None:
    """Why the wheel *filename* is not one of release *version* of
    *canonical*, or ``None``."""
    try:
        name, found, _build, _tags = parse_wheel_filename(filename)
    except (ValueError, InvalidVersion):
        return "not a valid wheel file name"
    if name != canonical or found != version:
        return "the file is not of this project and release"
    return None


def _sdist_mismatch(filename: str, canonical: str, version: Version) -> str | None:
    """Why the sdist *filename* is not one of release *version* of
    *canonical*, or ``None``."""
    try:
        name, found = parse_sdist_filename(filename)
    except (ValueError, InvalidVersion):
        return "not a valid sdist file name (.tar.gz or .zip)"
    if name != canonical or found != version:
        return "the file is not of this project and release"
    return None


def _declared_sha256(entry: Mapping[str, object]) -> str | None:
    """The SHA-256 *entry* declares, lower-case, or ``None``."""
    digests = entry.get("digests")
    value = digests.get("sha256") if isinstance(digests, dict) else None
    if isinstance(value, str) and _SHA256_RE.fullmatch(value):
        return value.lower()
    return None


def _read_entry(
    entry: object, canonical: str, version: Version
) -> ReleaseFile | tuple[str, str] | None:
    """*entry* of a release's file list as a :class:`ReleaseFile`; a
    ``(file name, why)`` when it is refused; ``None`` when it is neither a
    wheel nor an sdist (an egg, an installer), which is no candidate."""
    if not isinstance(entry, dict):
        return None
    kind = _PACKAGE_TYPES.get(str(entry.get("packagetype")))
    filename = entry.get("filename")
    if kind is None or not isinstance(filename, str):
        return None
    check = _wheel_mismatch if kind == WHEEL else _sdist_mismatch
    why = file_name_problem(filename) or check(filename, canonical, version)
    if why is not None:
        return filename, why
    url = entry.get("url")
    if not isinstance(url, str):
        return filename, "the answer gives no download URL"
    reason = entry.get("yanked_reason")
    return ReleaseFile(
        filename=filename,
        kind=kind,
        url=url,
        sha256=_declared_sha256(entry),
        yanked=entry.get("yanked") is True,
        yanked_reason=reason if isinstance(reason, str) and reason.strip() else None,
        tags=parse_wheel_filename(filename)[3] if kind == WHEEL else frozenset(),
    )


def read_files(
    entries: object, canonical: str, version: Version
) -> tuple[list[ReleaseFile], list[tuple[str, str]]]:
    """The wheels and sdists of the file list *entries* of release
    *version* of *canonical*, and each file refused with why, both sorted
    by file name. A list that is not a list holds no file; a file name it
    lists twice is refused once, and neither entry is a candidate."""
    files: list[ReleaseFile] = []
    refused: list[tuple[str, str]] = []
    for entry in entries if isinstance(entries, list) else []:
        read = _read_entry(entry, canonical, version)
        if isinstance(read, ReleaseFile):
            files.append(read)
        elif read is not None:
            refused.append(read)
    # A name listed twice could be either file: neither is a candidate, and
    # the name is refused once.
    counts = Counter([f.filename for f in files] + [name for name, _ in refused])
    twice = {name for name, count in counts.items() if count > 1}
    files = sorted(
        (f for f in files if f.filename not in twice), key=lambda f: f.filename
    )
    refused = sorted(
        [r for r in refused if r[0] not in twice] + [(n, _TWICE) for n in twice]
    )
    return files, refused


def _release_kind(
    key: str, entries: object, canonical: str
) -> tuple[str, Version] | None:
    """The kind of release *key* (:data:`STABLE`, :data:`PRERELEASE` or
    :data:`YANKED`) and its version, or ``None`` when it has no wheel or
    sdist with a digest, or its key is no PEP 440 version."""
    version = parse_version(key)
    if version is None:
        return None
    usable = [f for f in read_files(entries, canonical, version)[0] if f.sha256]
    if not usable:
        return None
    if all(f.yanked for f in usable):
        return YANKED, version
    return (PRERELEASE if version.is_prerelease else STABLE), version


def select_release(
    releases: Mapping[str, object], canonical: str
) -> ReleaseChoice | None:
    """The release to read when no version is given, from the ``releases``
    of the project's JSON answer, or ``None`` when none has a usable file."""
    order = {STABLE: 0, PRERELEASE: 1, YANKED: 2}
    found: list[tuple[int, Version, str, str]] = []
    for key, entries in releases.items():
        kind_version = _release_kind(key, entries, canonical)
        if kind_version is not None:
            kind, version = kind_version
            found.append((order[kind], version, key, kind))
    if not found:
        return None
    best = min(rank for rank, _version, _key, _kind in found)
    # The newest of the best kind; keys are unique, so two equal versions
    # (1.0 and 1.0.0) are told apart by their text.
    _rank, _version, key, kind = max(f for f in found if f[0] == best)
    return ReleaseChoice(version=key, kind=kind)


def versions_equal_to(releases: Mapping[str, object], version: Version) -> list[str]:
    """The keys of *releases* that are PEP 440 equal to *version*, sorted."""
    return sorted(key for key in releases if parse_version(key) == version)


def pick_wheel(files: Sequence[ReleaseFile]) -> WheelPick | None:
    """The wheel of *files* that best matches the running environment, or
    ``None`` when none does."""
    ranks: dict[Tag, int] = {}
    for index, tag in enumerate(_environment_tags()):
        ranks.setdefault(tag, index)
    ranked: list[tuple[bool, int, str, ReleaseFile]] = []
    for file in files:
        if file.kind != WHEEL:
            continue
        found = [ranks[tag] for tag in file.tags if tag in ranks]
        if found:
            ranked.append((file.yanked, min(found), file.filename, file))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[:3])
    return WheelPick(file=ranked[0][3], compatible=len(ranked))


def pick_sdist(files: Sequence[ReleaseFile]) -> SdistPick | None:
    """The sdist of *files* to read, or ``None`` when there is none."""
    sdists = sorted(
        (f for f in files if f.kind == SDIST),
        key=lambda f: (
            f.yanked,
            not f.filename.lower().endswith(".tar.gz"),
            f.filename,
        ),
    )
    return SdistPick(file=sdists[0], count=len(sdists)) if sdists else None
