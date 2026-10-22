# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for lock/pin file extractors
(:mod:`pitloom.extract.lock.poetry`, :mod:`pitloom.extract.lock.pylock`,
:mod:`pitloom.extract.lock.uv`, :mod:`pitloom.extract.lock.pdm`,
:mod:`pitloom.extract.lock.pipfile`, :mod:`pitloom.extract.lock.requirements`,
and future formats registered in
:mod:`pitloom.extract.lock.cascade`).

Every extraction step genuinely specific to one format (its own field
names, its own group/source-key conventions) stays in that format's own
module; only what's shared across two or more formats -- loading the
lock file, grouping entries by name, judging a specifier -- lives here.

See also: :mod:`pitloom.extract.lock._common_warnings` for the shared
``WARNING:`` message helpers, re-exported below.
"""

from __future__ import annotations

import json
import logging
import os
import stat
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, Literal, TypeGuard, TypeVar

from packaging.requirements import InvalidRequirement
from packaging.specifiers import SpecifierSet
from packaging.utils import InvalidName, canonicalize_name
from packaging.version import InvalidVersion, Version

from pitloom._toml_io import load_toml_bytes
from pitloom.core.pep508 import parse_requirement
from pitloom.extract._extract_utils import FETCH_MAX_BYTES, quote_source
from pitloom.extract.lock._common_warnings import (
    warn_conflicting_versions,
    warn_malformed_entry_not_table,
    warn_missing_name,
    warn_missing_version,
    warn_non_registry_source,
    warn_not_genuine_lock_file,
    warn_top_level_key_wrong_type,
)
from pitloom.logging_config import loggable, one_line

log = logging.getLogger(__name__)

__all__ = [
    "LockFileRefusedError",
    "POETRY_LOCK_SOURCE_NAME",
    "canonical_name_and_pinned_version",
    "default_group_included",
    "find_first_present_key",
    "group_by_canonical_name",
    "has_required_top_level_table",
    "is_format_version_number",
    "is_same_version",
    "is_usable_name",
    "is_usable_version",
    "load_lock_json",
    "load_lock_toml",
    "parse_exact_pin_requirement",
    "read_lock_bytes",
    "resolve_pinned_dependencies",
    "shape_validated_package",
    "single_exact_pin",
    "version_key",
    "warn_conflicting_versions",
    "warn_malformed_entry_not_table",
    "warn_missing_name",
    "warn_missing_version",
    "warn_non_registry_source",
    "warn_not_genuine_lock_file",
    "warn_top_level_key_wrong_type",
    "warn_unreadable_lock_file",
]

#: The literal ``Source:`` name written into
#: ``metadata.provenance["locked_dependencies"]`` for a ``poetry.lock``
#: result (by :func:`pitloom.extract.project.pyproject._try_read_poetry`) and
#: read back out of that same string (by
#: :func:`pitloom.extract.lock.cascade.apply_locked_dependencies`,
#: to look up ``poetry.lock``'s fixed rank when deciding whether a
#: cascade entry may override it). A single shared constant instead of
#: two independently-typed string literals -- editing one without the
#: other would silently break that rank lookup (it would just stop
#: matching, not raise), the "pattern hand-copied across 3+ call sites
#: drifts" problem CLAUDE.md warns about, here between a producer and a
#: consumer rather than three siblings.
POETRY_LOCK_SOURCE_NAME = "poetry.lock"

#: (path, mtime_ns, size) -> already-parsed lock data, for
#: :func:`load_lock_toml`/:func:`load_lock_json`. A format's pin extractor
#: and its hash-extraction companion (see
#: :mod:`pitloom.extract.lock.pylock_hash` and its siblings) both read and
#: parse the same winning lock file back-to-back within one cascade
#: lookup -- caching by the file's own current identity (not just its
#: path) means a second read within the same run is a dict lookup instead
#: of a re-parse, while a file that's changed or disappeared since the
#: last read (a different mtime/size, or a failed ``stat()``) is never
#: served stale: its cache key simply won't match, so it falls through to
#: a real re-read. Safe because every caller only reads the returned
#: dict, never mutates it. Holds only the :data:`_LOCK_FILE_CACHE_SIZE` most
#: recently used files (the pin pass, then the hash pass), so a long-lived
#: process does not accumulate every lock file it ever read.
_LockFileCacheKey = tuple[Path, int, int]
_LOCK_FILE_CACHE: dict[_LockFileCacheKey, dict[str, Any]] = {}
_LOCK_FILE_CACHE_SIZE = 2


def _lock_file_cache_key(lock_path: Path) -> _LockFileCacheKey | None:
    """Return *lock_path*'s current ``(path, mtime_ns, size)`` identity
    for :data:`_LOCK_FILE_CACHE`, or ``None`` when it can't be
    ``stat()``-ed (absent, permission error, etc.) -- callers treat
    ``None`` as "don't use the cache for this call" rather than raising,
    since the caller's own subsequent read attempt already handles that
    case.
    """
    try:
        stat_result = lock_path.stat()
    except OSError:
        return None
    return (lock_path, stat_result.st_mtime_ns, stat_result.st_size)


class LockFileRefusedError(ValueError):
    """A lock/pin file that is not read at all: not a regular file, or over
    :data:`~pitloom.extract._extract_utils.FETCH_MAX_BYTES`."""


def read_lock_bytes(lock_path: Path) -> bytes:
    """*lock_path*'s bytes, read through at most :data:`FETCH_MAX_BYTES` + 1.

    The type is checked before the open (Windows cannot open a directory) and
    again on the open descriptor, which is binary and non-blocking, so a FIFO
    swapped in for the file cannot hang the read and ``st_size`` is never
    trusted. Raises ``FileNotFoundError``, any other ``OSError``, or
    :class:`LockFileRefusedError` for a file that is not a regular file or is
    over the cap;
    every lock/pin reader logs its own ``WARNING:``."""
    if not stat.S_ISREG(os.stat(lock_path).st_mode):
        raise LockFileRefusedError("not a regular file")
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(lock_path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise LockFileRefusedError("not a regular file")
        handle = os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise
    with handle:
        raw = handle.read(FETCH_MAX_BYTES + 1)
    if len(raw) > FETCH_MAX_BYTES:
        raise LockFileRefusedError(f"over {FETCH_MAX_BYTES} bytes")
    return raw


def warn_unreadable_lock_file(lock_path: Path, exc: BaseException) -> None:
    """The one ``WARNING:`` for a lock/pin file that can't be read or
    parsed (*exc*: why): ``Cannot read`` for a file refused before parsing,
    ``Failed to parse`` otherwise."""
    verb = "Cannot read" if isinstance(exc, LockFileRefusedError) else "Failed to parse"
    log.warning("%s %s: %s", verb, quote_source(lock_path), one_line(exc))


def _load_lock(
    lock_path: Path, parse: Callable[[bytes], Any], kind: str
) -> dict[str, Any] | None:
    """Parse *lock_path*'s bytes with *parse* (a *kind* -- ``"TOML"`` or
    ``"JSON"`` -- reader), through :data:`_LOCK_FILE_CACHE`, returning
    ``None`` after one ``WARNING:`` for a file that is not a regular file,
    is over the size cap, can't be read or parsed (invalid UTF-8, nesting
    too deep for the parser, too large to hold) or whose top level isn't a
    table/object, and silently for an absent file."""
    cache_key = _lock_file_cache_key(lock_path)
    if cache_key is not None and cache_key in _LOCK_FILE_CACHE:
        data = _LOCK_FILE_CACHE.pop(cache_key)
        _LOCK_FILE_CACHE[cache_key] = data  # most recent last
        return data
    try:
        data = parse(read_lock_bytes(lock_path))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, RecursionError, MemoryError) as exc:
        # ValueError: the format's own decode error, a bare
        # UnicodeDecodeError for invalid UTF-8 and the reader's own
        # refusals alike -- a bad file, not a reason to abort the whole
        # cascade.
        warn_unreadable_lock_file(lock_path, exc)
        return None
    if not isinstance(data, dict):
        log.warning(
            "%s: top-level %s value is %s, expected an object",
            quote_source(lock_path),
            kind,
            type(data).__name__,
        )
        return None
    if cache_key is not None:
        if len(_LOCK_FILE_CACHE) >= _LOCK_FILE_CACHE_SIZE:
            del _LOCK_FILE_CACHE[next(iter(_LOCK_FILE_CACHE))]
        _LOCK_FILE_CACHE[cache_key] = data
    return data


def load_lock_toml(lock_path: Path) -> dict[str, Any] | None:
    """Load *lock_path* as TOML, returning ``None`` (after a
    ``WARNING:`` for an oversized or unparseable file, silently for a
    simply-absent one) instead of raising -- every lock format is optional
    enrichment, never a requirement, so a caller's usual next step is
    ``if data is None: return []``.

    See :data:`_LOCK_FILE_CACHE` for the memoization this and
    :func:`load_lock_json` share.
    """
    return _load_lock(lock_path, load_toml_bytes, "TOML")


def load_lock_json(lock_path: Path) -> dict[str, Any] | None:
    """Read and parse *lock_path* as JSON, returning ``None`` (after a
    ``WARNING:`` for an oversized, unparseable or wrong-shaped file,
    silently for a simply-absent one) instead of raising -- the
    JSON-format counterpart of :func:`load_lock_toml`, for
    ``Pipfile.lock`` (JSON, unlike every other lock/pin format this
    module serves, which are TOML).

    JSON's top level can legally be an array, string, number, or
    ``null`` (TOML's grammar guarantees a table), so a non-object is
    rejected with a ``WARNING:`` and every caller can rely on this
    function's declared ``dict[str, Any] | None`` return type without
    its own defensive `isinstance` check.
    """
    return _load_lock(lock_path, json.loads, "JSON")


def is_format_version_number(value: object) -> bool:
    """Return whether *value* is an integer format version -- ``int`` but
    not ``bool``, which ``isinstance`` also accepts (``version = true``)."""
    return isinstance(value, int) and not isinstance(value, bool)


def has_required_top_level_table(
    data: dict[str, Any],
    table_key: str,
    required_key: str,
    value_type: type | tuple[type, ...] = object,
) -> bool:
    """Return whether *data* has a top-level table *table_key* containing
    key *required_key* with a value that's an instance of *value_type* --
    the "does this look like a genuine file of this format" shape check
    every TOML/JSON-based lock extractor needs before treating an empty
    ``[[package]]``-style list as an authoritative, zero-dependency
    result.

    A format-defining key absent entirely is ambiguous on its own -- the
    shape is identical whether the lock genuinely resolves to zero
    packages (rare, but every genuine lock-writer tool still emits its
    own identifying top-level structure for that case) or the file is
    some unrelated, syntactically-valid document that merely happens to
    be named/found as this format's lock file (e.g. truncated,
    hand-edited, or from an unrelated tool). Checking for the format's
    own marker distinguishes "genuinely this format, zero dependencies"
    from "not actually this format", so the latter can't silently win
    the cascade over a genuinely usable lower-priority lock format via a
    spurious authoritative-empty result -- e.g. ``poetry.lock``'s
    string-valued ``metadata.lock-version``, ``pdm.lock``'s
    string-valued ``metadata.lock_version``, ``Pipfile.lock``'s
    int-valued ``_meta.pipfile-spec`` (each caller passes its own
    format's real value type as *value_type*; a key present with a value
    of the wrong shape is exactly as ambiguous as the key being absent
    entirely, so it isn't treated as a looser pass than outright
    absence).
    """
    table = data.get(table_key)
    if not isinstance(table, dict):
        return False
    value = table.get(required_key)
    # A boolean is never a format marker, whatever *value_type*.
    return isinstance(value, value_type) and not isinstance(value, bool)


def version_key(version: str) -> Version | str:
    """Return a hashable key for *version* that compares equal under PEP 440
    equivalences (e.g. ``"1.0" == "1.0.0"``), falling back to the raw string
    when it does not parse as a PEP 440 version."""
    try:
        return Version(version)
    except (InvalidVersion, TypeError):
        return version


def is_usable_name(name: object) -> TypeGuard[str]:
    """Return whether *name* is a valid PEP 508 distribution name -- the
    check every lock/pin extractor applies to an entry's ``name`` before it
    reaches a PURL, a ``name==version`` dependency string or a log line
    (``a @ url``, ``a[x]``, ``a; marker``, a name with a newline or control
    character all fail). Each call site still logs its own ``WARNING:``
    when this returns ``False`` (:func:`warn_missing_name`)."""
    if not isinstance(name, str):
        return False
    try:
        canonicalize_name(name, validate=True)
    except InvalidName:
        return False
    return True


def is_usable_version(version: object) -> TypeGuard[str]:
    """Return whether *version* is a non-empty string that parses as a
    valid PEP 440 version -- the "can this become a real
    ``name==version`` pin" check every lock/pin extractor applies to a
    ``[[package]]`` entry's ``version`` field before using it. Rejects
    not just non-strings but a syntactically-string-yet-not-a-version
    value too (whitespace, a version padded with whitespace, ``"*"``,
    ``"not a version"``) -- without this,
    a malformed lock entry would silently produce an invalid
    ``name==<garbage>`` dependency/PURL instead of being warned and
    skipped like every other malformed-field case. Each call site still
    logs its own ``WARNING:`` when this returns ``False``, since the
    message wording (which field, which format) is genuinely
    format-specific.

    Typed as a :class:`typing.TypeGuard`\\ [``str``] so a caller's usual
    ``if not is_usable_version(version): return None`` early-return
    narrows *version* to ``str`` for the rest of the function, instead
    of needing its own redundant ``isinstance`` check before passing
    *version* to something that requires ``str``.
    """
    if not isinstance(version, str) or not version or version != version.strip():
        return False
    try:
        Version(version)
    except InvalidVersion:
        return False
    return True


_CanonicalGroupT = TypeVar("_CanonicalGroupT", bound=tuple[str, ...])


def group_by_canonical_name(
    items: Iterable[_CanonicalGroupT],
) -> dict[str, list[_CanonicalGroupT]]:
    """Group tuples by PEP 503-canonicalized *name* (each tuple's first
    element), preserving file order both across and within groups.

    Comparing canonicalized (lowercased, ``-``/``_``/``.``-folded) names
    is required, not optional: ``Flask==1.0`` and ``flask==2.0`` name the
    same PyPI package under PEP 503, so a caller checking "does this name
    resolve to more than one version" must group them together or the
    check silently never fires for a mixed-case duplicate.

    Generic over tuple arity so :func:`resolve_pinned_dependencies`'s
    ``(name, version)`` pairs and ``(name, operator, version)`` triples
    and :mod:`pitloom.assemble.spdx3._document_locked_deps`'s
    ``(name, dep, pinned)`` triples share one implementation instead of a
    per-caller copy of the same loop.

    A caller decides what a multi-entry group means for its own format:
    :mod:`pitloom.extract.lock.pdm` collapses a group to one entry when
    every version agrees (its per-extra duplicate records always do) and
    skips just that name otherwise; ``requirements.txt`` treats any
    conflicting group as disqualifying its whole file.
    """
    by_canonical: dict[str, list[_CanonicalGroupT]] = {}
    for item in items:
        by_canonical.setdefault(canonicalize_name(item[0]), []).append(item)
    return by_canonical


#: PEP 440 operators that pin to exactly one release: ``==`` (the
#: ordinary case) and ``===`` (arbitrary-equality, for a legacy/
#: non-normalizable version string a resolver would otherwise reject --
#: rare in practice, but just as exact a pin as ``==`` once present).
_EXACT_PIN_OPERATORS = frozenset({"==", "==="})


def is_same_version(v1: str, v2: str) -> bool:
    """Return whether two version strings represent the same release.

    Uses :class:`packaging.version.Version` comparison so PEP 440
    equivalences (e.g. ``"1.0" == "1.0.0"``) compare equal rather than
    triggering spurious version-conflict warnings. Falls back to exact
    string comparison when either string is not a valid PEP 440 version
    (e.g. arbitrary-equality ``===`` strings).
    """
    try:
        return Version(v1) == Version(v2)
    except (InvalidVersion, TypeError):
        return v1 == v2


def single_exact_pin(specifier_set: SpecifierSet) -> tuple[str, str] | None:
    """Return ``(operator, version)`` when *specifier_set* contains exactly
    one non-wildcard exact-pin specifier (``==`` or PEP 440's arbitrary-
    equality ``===``, e.g. ``SpecifierSet("==2.31.0")`` ->
    ``("==", "2.31.0")``, ``SpecifierSet("===2021.01.01-legacy")`` ->
    ``("===", "2021.01.01-legacy")``), or ``None`` for anything looser than
    one exact pin -- a range, more than one specifier, or a prefix-match
    wildcard like ``"==2.31.*"`` (``packaging.specifiers.Specifier`` reports
    that as operator ``"=="`` too, but it pins a *range* of versions, not
    one exact release -- ``===`` has no wildcard form, so this check only
    matters for ``==``).

    Doesn't itself construct *specifier_set* from a raw string --
    :mod:`pitloom.extract.lock.pipfile` and
    :mod:`pitloom.extract.lock.requirements` both need a raw-string
    parse step first, and each wants different ``WARNING:`` wording for
    "unparseable" vs. "parseable but not a single exact pin" -- so
    parsing (and catching ``packaging.specifiers.InvalidSpecifier``)
    stays the caller's job; this function only judges an already-built
    ``SpecifierSet``.
    """
    specifiers = list(specifier_set)
    if (
        len(specifiers) != 1
        or specifiers[0].operator not in _EXACT_PIN_OPERATORS
        or "*" in specifiers[0].version
    ):
        return None
    return specifiers[0].operator, specifiers[0].version


def parse_exact_pin_requirement(req_str: str) -> tuple[str, str, str] | None:
    """Parse a PEP 508 dependency string and return ``(name, operator, version)``
    when it represents a single exact ``==`` or ``===`` pin without a direct URL
    reference, or ``None`` otherwise."""
    try:
        req = parse_requirement(req_str)
    except (InvalidRequirement, TypeError):
        return None
    if req.url is not None:
        return None
    pin = single_exact_pin(req.specifier)
    if pin is None:
        return None
    op, version = pin
    return req.name, op, version


def canonical_name_and_pinned_version(dep: str) -> tuple[str, str] | None:
    """Parse an exact-pin dependency string -- one already known to carry a
    single exact pin, as every lock/pin extractor in this package formats
    its own output (e.g. ``f"{name}=={version}"``) -- back into
    ``(canonicalize_name(name), version)``, or ``None`` if it doesn't parse
    or isn't a single exact pin.

    Used by each format's hash-extraction companion
    (:mod:`pitloom.extract.lock.pylock_hash` and its siblings) to look a pin
    extractor's own already-resolved winning dependency back up in the raw
    lock data by name and version, so hash extraction never re-derives the
    pin extractor's own group/marker/non-registry-source filtering and
    conflicting-version exclusion a second time -- it only ever computes a
    hash for a package the pin extractor itself decided to include.
    """
    parsed = parse_exact_pin_requirement(dep)
    if parsed is None:
        return None
    name, _op, version = parsed
    return canonicalize_name(name), version


def _pin_operator(pin: tuple[str, str] | tuple[str, str, str]) -> str:
    """*pin*'s operator, ``"=="`` for a ``(name, version)`` pair."""
    return pin[1] if len(pin) == 3 else "=="


def _same_pin(
    pin: tuple[str, str] | tuple[str, str, str], op: str, version: str
) -> bool:
    """Whether *pin* names the release ``(op, version)`` does: PEP 440
    equality, except that a ``===`` (arbitrary equality) on either side
    compares the exact string (``===1.0`` is not ``1.0.0``)."""
    if "===" in (op, _pin_operator(pin)):
        return pin[-1] == version
    return is_same_version(pin[-1], version)


def resolve_pinned_dependencies(
    pins: Iterable[tuple[str, str] | tuple[str, str, str]],
    lock_file: str | Path,
    *,
    on_conflict: Literal["skip", "abort"] = "skip",
) -> list[str] | None:
    """Group pinned package tuples by canonical name, verify PEP 440 version
    consistency across same-name entries, and format each into an exact-pin
    PEP 508 string (``name==version`` or ``name<op>version``).

    Parameters:
        pins: An iterable of ``(name, version)`` pairs or ``(name, op, version)``
            triples. When pairs are passed, the operator defaults to ``"=="``.
        lock_file: Label for log messages (e.g. ``"poetry.lock"`` or the file's
            :class:`pathlib.Path`).
        on_conflict: Conflict handling policy when a canonical name has multiple
            entries with distinct PEP 440 versions:
            - ``"skip"``: Emit a warning, omit the conflicting package, and
              continue resolving remaining packages (standard for lock files).
            - ``"abort"``: Emit a warning and immediately return ``None``,
              disqualifying the whole file (standard for ``requirements.txt``).
    """
    file_label = lock_file.name if isinstance(lock_file, Path) else str(lock_file)
    dependencies: list[str] = []
    for group in group_by_canonical_name(pins).values():
        first = group[0]
        name = first[0]
        version = first[-1]
        op = _pin_operator(first)
        conflicting_versions = {
            item[-1] for item in group if not _same_pin(item, op, version)
        }
        all_versions = {item[-1] for item in group}

        if conflicting_versions:
            if on_conflict == "abort":
                log.warning(
                    "%s: %r pinned to conflicting versions (%s) -- ignoring %s",
                    quote_source(lock_file),
                    name,
                    loggable(", ".join(sorted(all_versions))),
                    file_label,
                )
                return None
            warn_conflicting_versions(file_label, name, all_versions)
            continue
        dependencies.append(f"{name}{op}{version}")
    return dependencies


def find_first_present_key(
    mapping: Mapping[str, object], keys: Iterable[str]
) -> str | None:
    """Return the first of *keys* (in order) that's a key of *mapping*,
    or ``None`` if none are.

    Every *key-presence* non-registry-source check (``pylock.toml``'s
    top-level ``vcs``/``directory``/``archive`` keys, ``uv.lock``'s
    nested ``source.{key}``, ``pdm.lock``'s flat ``git``/``path``/``url``
    keys) reduces to this same "which non-registry marker, if any, is
    present" lookup once the caller has the right mapping and key tuple
    for its own format -- factored out so a shared key list update (e.g.
    adding a newly-noticed key like ``"url"``) can be a one-line change
    in one format's own key tuple without also re-deriving this lookup
    itself at each call site. ``poetry.lock``'s own non-registry check is
    a different shape (single-field *value* membership on
    ``source.type``, not presence of any of several keys) and doesn't
    use this helper.
    """
    return next((key for key in keys if key in mapping), None)


def shape_validated_package(
    pkg: object, lock_file: str, entry_label: str = "[[package]]"
) -> dict[str, Any] | None:
    """Return *pkg* itself when it's a well-formed, versioned
    list-of-tables entry -- ``None`` (with a ``WARNING:``) for a
    non-table entry, or one with a missing/invalid ``name`` or
    missing/unparseable ``version``.

    Shared by every lock format whose per-package entries are a flat
    table with a plain ``name``/``version`` pair (``poetry.lock``,
    ``pdm.lock``) -- factored out of two independently-drifting,
    near-identical per-format copies so a wording/behavior change to
    this check lands once instead of needing to be repeated at each
    format's own call site.
    """
    if not isinstance(pkg, dict):
        warn_malformed_entry_not_table(lock_file, entry_label, pkg)
        return None
    name = pkg.get("name")
    if not is_usable_name(name):
        warn_missing_name(f"Skipping malformed {lock_file} {entry_label} entry", name)
        return None
    version = pkg.get("version")
    if not is_usable_version(version):
        warn_missing_version(lock_file, name)
        return None
    return pkg


def default_group_included(
    validated: Mapping[str, object], lock_file: str, default_group: str, name: str
) -> bool | None:
    """Return whether *validated* (an already shape-validated package
    entry) belongs to *default_group* per its ``groups`` list -- ``None``
    (with a ``WARNING:``) when ``groups`` is present but not a list.

    Shared by every lock format whose per-package group membership is a
    flat ``groups`` list defaulting to a single-element list naming the
    format's own default group (``poetry.lock``'s ``"main"``,
    ``pdm.lock``'s ``"default"``) -- factored out of two
    independently-drifting, near-identical per-format copies the same
    way :func:`shape_validated_package` was.
    """
    groups = validated.get("groups", [default_group])
    if not isinstance(groups, list):
        log.warning(
            "Skipping malformed %s entry %r: 'groups' is %s, expected a list",
            lock_file,
            name,
            type(groups).__name__,
        )
        return None
    return default_group in groups
