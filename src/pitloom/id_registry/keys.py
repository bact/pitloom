# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Loom ID registry keys: the one place every surface computes them.

An artifact with a file or directory below the registry's project root is
keyed by its path from that root (tier 1, :func:`path_key`); anything else
keeps its name (tier 2). A path key is ``/``-separated, NFC, never
case-folded. A layout alias (:func:`is_layout_alias`) is the same file
under a ``src/`` or ``lib/`` layout's installed path (:data:`LAYOUT_ROOTS`).

See also: :mod:`pitloom.id_registry.resolve` (registry resolution),
:func:`pitloom.core.walk_rules.shortened_by` (the layout rule).
"""

from __future__ import annotations

import os
import posixpath
import unicodedata
from enum import Enum
from pathlib import Path, PurePath, PurePosixPath
from typing import TYPE_CHECKING, NamedTuple

from pitloom.core.file_identity import file_id
from pitloom.core.path_confine import inside_ancestor
from pitloom.core.project import project_relative_or_fallback
from pitloom.core.walk_rules import shortened_by

if TYPE_CHECKING:
    from pitloom.core.project import FilesOrigin, ProjectFile
    from pitloom.id_registry._registry import IdRegistry

__all__ = [
    "LAYOUT_ALIAS_HITS_INFO",
    "LAYOUT_ALIAS_PROMOTED_INFO",
    "LAYOUT_ROOTS",
    "Alias",
    "LookupKey",
    "alias_candidates",
    "alias_tail",
    "artifact_key",
    "file_lookup_key",
    "is_layout_alias",
    "join_key",
    "on_disk_path",
    "path_key",
    "project_prefix",
]

#: The suffix of a wheel's ``<name>-<version>.data`` directory: its members
#: install outside the package, so they have no layout alias.
_DATA_DIR_SUFFIX = ".data"

#: The top directories of a layout whose installed path drops them: the
#: only first parts a layout alias cuts. Another layout (``python/``,
#: ``packages/``) has none: a wheel-only run mints its own ids for its
#: files, two keys rather than one id taken from another file.
LAYOUT_ROOTS = ("src", "lib")

#: ``log.info()`` format for a document's elements (files, models) that
#: matched a held key through a layout alias. Argument: their count.
LAYOUT_ALIAS_HITS_INFO = (
    "ID registry: %d element(s) matched a registry key through the src/lib layout alias"
)
#: ``log.info()`` format for the held keys ``id generate`` moved to their
#: canonical key. Argument: their count.
LAYOUT_ALIAS_PROMOTED_INFO = "ID registry: %d key(s) promoted from a layout alias"


class Alias(Enum):
    """Which other key a lookup may also hit: none; the held layout alias
    of a canonical key, to be replaced by it; or the held key a layout
    path is the alias of."""

    NONE = "none"
    CANONICAL = "canonical"
    LAYOUT = "layout"


class LookupKey(NamedTuple):
    """A registry key to look up: *key*, the *alias* it may also hit,
    whether it is a path key (*path*, tier 1) or a name (tier 2), and the
    project prefix (*base*, :func:`project_prefix`; ``""``: the registry's
    root) below which its layout alias is taken."""

    key: str
    alias: Alias = Alias.NONE
    path: bool = False
    base: str = ""


def _nfc(text: str) -> str:
    """*text* in Unicode normalisation form C."""
    return unicodedata.normalize("NFC", text)


def _listdir(directory: str) -> list[str]:
    """The names in *directory* (a seam for tests)."""
    return os.listdir(directory)


def _below(path: PurePath, root: PurePath) -> tuple[PurePath, tuple[str, ...]] | None:
    """*path*'s ancestor that is *root* (by spelling or identity) and the
    parts below it; ``None`` outside *root* (another drive included)."""
    ancestor = inside_ancestor(path, root)
    return None if ancestor is None else (ancestor, path.relative_to(ancestor).parts)


def _below_root(
    root: PurePath, path: str | os.PathLike[str]
) -> tuple[PurePath, tuple[str, ...]] | None:
    """:func:`_below` of *path* lexically (``..`` collapsed, no symlink
    followed), else through ``os.path.realpath``. A relative *path* is
    taken from the current directory; ``None`` when that is deleted."""
    try:
        base = "" if PurePath(path).is_absolute() else os.getcwd()
    except OSError:  # the current directory was deleted
        return None
    lexical = PurePath(os.path.normpath(os.path.join(base, path)))
    found = _below(lexical, root)
    if found is not None:
        return found
    try:
        real = PurePath(os.path.realpath(lexical))
    except ValueError:  # a NUL: no file to resolve
        return None
    return _below(real, root)


def _fold(name: str) -> str:
    """*name* as a case-insensitive file system may compare it: only to
    choose the names worth an identity check, never a key."""
    return _nfc(name).casefold()


def _on_disk_name(directory: str, name: str) -> str:
    """*name* in *directory* as the directory lists it: as given when
    listed so; else the first in sort order of the listed names that fold
    alike and are the same file (by identity); else as given (unlistable,
    missing, or no identity)."""
    try:
        names = _listdir(directory)
    except (OSError, ValueError):
        return name
    if name in names:
        return name
    wanted = file_id(os.path.join(directory, name))
    if wanted is None:
        return name
    folded = _fold(name)
    same = sorted(
        listed
        for listed in names
        if _fold(listed) == folded
        and file_id(os.path.join(directory, listed)) == wanted
    )
    return same[0] if same else name


def _on_disk(ancestor: PurePath, parts: tuple[str, ...]) -> list[str]:
    """*parts* below *ancestor*, each spelt as its directory lists it."""
    directory, spelt = os.fspath(ancestor), []
    for part in parts:
        name = _on_disk_name(directory, part)
        spelt.append(name)
        directory = os.path.join(directory, name)
    return spelt


def path_key(
    registry: IdRegistry, path: str | os.PathLike[str], *, on_disk: bool = False
) -> str | None:
    """*path*'s key in *registry*: its path from
    :meth:`~pitloom.id_registry.IdRegistry.root_dir`, ``/``-separated and
    NFC; ``"."`` for the root itself; ``None`` outside the root (another
    drive or UNC share included), and when there is no root (the current
    directory was deleted). Never raises.

    A relative *path* is taken from the current directory (``None`` when
    that is deleted). Lexically first (``..`` collapsed, no symlink
    followed: an in-root symlink keys by its own location), the root
    matched by spelling or identity (macOS ``/tmp`` is ``/private/tmp``;
    another case); else through ``os.path.realpath`` (a symlink from
    outside into the root). With *on_disk*, each part below the root is
    spelt as its parent directory lists it (a user-typed ``DATA/T.TXT`` on
    a case-insensitive file system keys as ``data/t.txt``); a part that
    cannot be matched keeps its spelling. Never case-folded.
    """
    try:
        root = PurePath(registry.root_dir())
    except OSError:  # no project root, and the current directory was deleted
        return None
    found = _below_root(root, path)
    if found is None:
        return None
    ancestor, parts = found
    spelt = _on_disk(ancestor, parts) if on_disk else parts
    return _nfc("/".join(spelt) or ".")


def on_disk_path(root: Path, path: Path) -> Path:
    """*path* (``..`` collapsed lexically) with each part below *root*
    spelt as its directory lists it, the on-disk step of :func:`path_key`
    (no NFC: the result is opened); as given when not below *root*."""
    found = _below(PurePath(os.path.normpath(path)), PurePath(root))
    if found is None:
        return path
    ancestor, parts = found
    return Path(ancestor, *_on_disk(ancestor, parts))


def project_prefix(
    registry: IdRegistry, project_dir: str | os.PathLike[str]
) -> str | None:
    """*project_dir*'s key in *registry* (:func:`path_key`, on-disk
    spelling) as a :func:`join_key` prefix: ``""`` for the root itself;
    ``None`` outside the root."""
    key = path_key(registry, project_dir, on_disk=True)
    return None if key is None else ("" if key == "." else key)


def join_key(prefix: str, rel: str) -> str | None:
    """The key of the ``/``-separated project-relative path *rel* in a
    project whose :func:`project_prefix` is *prefix*: joined, ``..``
    collapsed lexically, NFC. ``None`` for an absolute *rel* (a drive
    included) or one leading outside the root."""
    if (
        PurePosixPath(rel).is_absolute()
        or os.path.isabs(rel)
        or os.path.splitdrive(rel)[0]
    ):
        return None
    joined = posixpath.normpath(posixpath.join(prefix, rel))
    if joined == ".." or joined.startswith("../"):
        return None
    return _nfc(joined)


def artifact_key(
    registry: IdRegistry,
    *,
    path: str | os.PathLike[str] | None,
    name: str,
    alias: Alias = Alias.NONE,
) -> LookupKey:
    """The key an artifact is looked up by: its :func:`path_key` (on-disk
    spelling) with *alias* when *path* exists below the root; else *name*,
    with no alias."""
    if path is not None and os.path.lexists(path):
        key = path_key(registry, path, on_disk=True)
        if key is not None:
            return LookupKey(key, alias, path=True)
    return LookupKey(name)


def _key_parts(key: str) -> list[str] | None:
    """*key*'s ``/``-separated parts; ``None`` when it is no clean relative
    path (an empty, ``.`` or ``..`` part)."""
    parts = key.split("/")
    return None if any(p in ("", ".", "..") for p in parts) else parts


def _below_base(key: str, base: str) -> str | None:
    """*key* below the project prefix *base* (all of it for ``""``);
    ``None`` when it is not below."""
    if not base:
        return key
    return key[len(base) + 1 :] if key.startswith(f"{base}/") else None


def _on_base(base: str, rel: str) -> str:
    """*rel* below the project prefix *base*."""
    return f"{base}/{rel}" if base else rel


def alias_tail(key: str, base: str = "") -> str | None:
    """The key *key* would have as a layout's installed path: without the
    first part below the project prefix *base* when that is one of
    :data:`LAYOUT_ROOTS` and a directory and a file remain
    (:func:`~pitloom.core.walk_rules.shortened_by`); ``None`` otherwise,
    for a key not below *base*, and for a ``*.data`` part among those first
    two (a wheel's ``.data`` member installs outside the package)."""
    rel = _below_base(key, base)
    parts = None if rel is None else _key_parts(rel)
    if (
        parts is None
        or parts[0] not in LAYOUT_ROOTS
        or any(p.endswith(_DATA_DIR_SUFFIX) for p in parts[:2])
    ):
        return None
    tail = parts[1:]
    if shortened_by(parts, tail) != 1:
        return None
    return _on_base(base, "/".join(tail))


def is_layout_alias(first: str, second: str) -> bool:
    """Whether one key is the other's :func:`alias_tail`. A key is not its
    own alias."""
    return alias_tail(first) == second or alias_tail(second) == first


def _alias_pairs(key: str, base: str) -> list[tuple[str, str]]:
    """Each key that is a layout alias of *key* below the project prefix
    *base*, with the shorter key of the two: *key*'s :func:`alias_tail`,
    then *key*'s part below *base* under each of :data:`LAYOUT_ROOTS`."""
    pairs = []
    tail = alias_tail(key, base)
    if tail is not None:
        pairs.append((tail, tail))
    rel = _below_base(key, base)
    for root in LAYOUT_ROOTS if rel is not None else ():
        longer = _on_base(base, f"{root}/{rel}")
        if alias_tail(longer, base) == key:
            pairs.append((longer, key))
    return pairs


def alias_candidates(
    registry: IdRegistry,
    type_name: str,
    key: str,
    sha256: str | None,
    *,
    root: str | os.PathLike[str] | None = None,
    base: str = "",
) -> tuple[str, ...]:
    """The held keys of *type_name* in *registry* that are layout aliases
    of *key* (NFC) below the project prefix *base* (:func:`alias_tail`) in
    either direction and record *sha256* (any case), sorted; none when
    *sha256* is ``None`` (an ungated lookup has no alias). Each is one
    dictionary lookup, never a scan.

    A pair whose shorter key (a full key) names a file or directory below
    *root* (by default :meth:`~pitloom.id_registry.IdRegistry.root_dir`;
    none when that raises) is two files, not an alias, and is left out."""
    if sha256 is None:
        return ()
    wanted, key = sha256.lower(), _nfc(key)
    found = []
    for held, shorter in _alias_pairs(key, base):
        entry = registry.get(type_name, held)
        if entry is not None and entry.sha256 == wanted:
            found.append((held, shorter))
    if not found:
        return ()
    try:
        top = os.fspath(registry.root_dir() if root is None else root)
    except OSError:  # no project root, and the current directory was deleted
        return ()
    return tuple(
        sorted(
            held
            for held, shorter in found
            if not os.path.lexists(os.path.join(top, shorter))
        )
    )


def _distribution_key(distribution_path: str, prefix: str | None) -> LookupKey:
    """The key of a file with no project path: its *distribution_path*,
    below the project *prefix* when one is known, looking for a held key
    it is the layout alias of below that prefix; a ``*.data`` member has
    none."""
    first = distribution_path.split("/", 1)[0]
    alias = Alias.NONE if first.endswith(_DATA_DIR_SUFFIX) else Alias.LAYOUT
    if prefix is not None:
        key = join_key(prefix, distribution_path)
        if key is not None:
            return LookupKey(key, alias, path=True, base=prefix)
    return LookupKey(_nfc(distribution_path), alias, path=True)


def _sdist_key(pf: ProjectFile) -> LookupKey:
    """The key of an sdist member: its project-relative ``physical_path``
    (the sdist's top directory is the project root). Only a member whose
    top directory was cut may replace a held layout alias: an uncut name's
    first part is that top directory, not ``src/``."""
    key = join_key("", pf.physical_path)
    if key is None:
        return LookupKey(pf.physical_path)
    cut = pf.distribution_path.endswith(f"/{pf.physical_path}")
    return LookupKey(key, Alias.CANONICAL if cut else Alias.NONE, path=True)


def _project_key(
    pf: ProjectFile, prefix: str | None, registry: IdRegistry | None
) -> LookupKey:
    """The key of a project file (see :func:`file_lookup_key`)."""
    if prefix is not None:
        key = join_key(prefix, pf.physical_path)
        if key is not None:
            return LookupKey(key, Alias.CANONICAL, path=True, base=prefix)
    if registry is not None and PurePath(pf.physical_path).is_absolute():
        key = path_key(registry, pf.physical_path)
        if key is not None:
            return LookupKey(key, Alias.CANONICAL, path=True)
    return LookupKey(
        project_relative_or_fallback(pf.physical_path, pf.distribution_path)
    )


def file_lookup_key(
    pf: ProjectFile,
    origin: FilesOrigin,
    prefix: str | None,
    registry: IdRegistry | None = None,
) -> LookupKey:
    """The key a ``software_File`` *pf* is looked up and harvested under,
    on every surface. *prefix* is the project directory's
    :func:`project_prefix`, computed once per document (``None`` without a
    registry, project directory, or outside the root); a key joined to it
    takes its layout alias below it (``LookupKey.base``).

    - a wheel member (*origin* an archive, not an sdist) or a file a build
      extracted (``pf.built``): its ``distribution_path``, joined to
      *prefix* when there is one (an embed's project directory; none for a
      wheel read alone), ``LAYOUT`` alias (none for a ``*.data`` member);
    - an sdist member: its ``physical_path`` (the top directory cut),
      ``CANONICAL`` alias when the top directory was cut;
    - a project file: :func:`join_key` of *prefix* and its
      ``physical_path``, ``CANONICAL`` alias; one outside the project
      (an absolute ``physical_path``) below *registry*'s root: its
      :func:`path_key`, ``CANONICAL`` alias; otherwise its
      :func:`~pitloom.core.project.project_relative_or_fallback` path with
      no alias.
    """
    if origin.sdist:
        return _sdist_key(pf)
    if origin.archive or pf.built:
        return _distribution_key(pf.distribution_path, prefix)
    return _project_key(pf, prefix, registry)
