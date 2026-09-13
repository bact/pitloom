# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for lock/pin file extractors
(:mod:`pitloom.extract._poetry_lock`, :mod:`pitloom.extract._pylock`,
:mod:`pitloom.extract._uv_lock`, :mod:`pitloom.extract._pdm_lock`,
:mod:`pitloom.extract._pipfile_lock`, :mod:`pitloom.extract._requirements_txt`,
and future formats registered in
:mod:`pitloom.extract._locked_dependencies`).

Every extraction step genuinely specific to one format (its own field
names, its own group/source-key conventions) stays in that format's own
module; only what's shared across two or more formats -- loading the
lock file, grouping entries by name, judging a specifier -- lives here.

See also: :mod:`pitloom.extract._lock_common_warnings` for the shared
``WARNING:`` message helpers, re-exported below.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, TypeGuard, TypeVar

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from pitloom.extract._lock_common_warnings import (
    warn_conflicting_versions,
    warn_malformed_entry_not_table,
    warn_missing_name,
    warn_missing_version,
    warn_non_registry_source,
    warn_not_genuine_lock_file,
    warn_top_level_key_wrong_type,
)
from pitloom.extract._toml_io import TOMLDecodeError, load_toml_file

log = logging.getLogger(__name__)

__all__ = [
    "POETRY_LOCK_SOURCE_NAME",
    "canonical_name_and_pinned_version",
    "default_group_included",
    "find_first_present_key",
    "group_by_canonical_name",
    "group_pin_triples_by_canonical_name",
    "group_versions_by_canonical_name",
    "has_required_top_level_table",
    "index_packages_by_name",
    "index_packages_by_name_and_version",
    "is_same_version",
    "is_usable_version",
    "load_lock_json",
    "load_lock_toml",
    "sha256_file_entry_candidates",
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
]

#: The literal ``Source:`` name written into
#: ``metadata.provenance["locked_dependencies"]`` for a ``poetry.lock``
#: result (by :func:`pitloom.extract._pyproject._try_read_poetry`) and
#: read back out of that same string (by
#: :func:`pitloom.extract._locked_dependencies.apply_locked_dependencies`,
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
#: :mod:`pitloom.extract._pylock_hashes` and its siblings) both read and
#: parse the same winning lock file back-to-back within one cascade
#: lookup -- caching by the file's own current identity (not just its
#: path) means a second read within the same run is a dict lookup instead
#: of a re-parse, while a file that's changed or disappeared since the
#: last read (a different mtime/size, or a failed ``stat()``) is never
#: served stale: its cache key simply won't match, so it falls through to
#: a real re-read. Safe because every caller only reads the returned
#: dict, never mutates it.
_LockFileCacheKey = tuple[Path, int, int]
_LOCK_FILE_CACHE: dict[_LockFileCacheKey, dict[str, Any]] = {}


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


def load_lock_toml(lock_path: Path) -> dict[str, Any] | None:
    """Load *lock_path* as TOML, returning ``None`` (after a
    ``WARNING:`` for a parse/read failure, silently for a simply-absent
    file) instead of raising -- every lock format is optional
    enrichment, never a requirement, so a caller's usual next step is
    ``if data is None: return []``.

    See :data:`_LOCK_FILE_CACHE` for the memoization this and
    :func:`load_lock_json` share.
    """
    cache_key = _lock_file_cache_key(lock_path)
    if cache_key is not None:
        cached = _LOCK_FILE_CACHE.get(cache_key)
        if cached is not None:
            return cached
    try:
        data = load_toml_file(lock_path)
    except FileNotFoundError:
        return None
    except (OSError, TOMLDecodeError, UnicodeDecodeError) as exc:
        # tomllib/tomli's underlying decode step raises a bare
        # UnicodeDecodeError (not its own TOMLDecodeError) for invalid
        # UTF-8 bytes -- still just a malformed/unparseable file, not a
        # reason to abort the whole cascade.
        log.warning("Failed to parse %s: %s", lock_path, exc)
        return None
    if cache_key is not None:
        _LOCK_FILE_CACHE[cache_key] = data
    return data


def load_lock_json(lock_path: Path) -> dict[str, Any] | None:
    """Read and parse *lock_path* as JSON, returning ``None`` (after a
    ``WARNING:`` for a parse/read or shape failure, silently for a
    simply-absent file) instead of raising -- the JSON-format
    counterpart of :func:`load_lock_toml`, for ``Pipfile.lock`` (JSON,
    unlike every other lock/pin format this module serves, which are
    TOML).

    Unlike TOML (whose grammar guarantees a table at the document root,
    so this can't happen to :func:`load_lock_toml`), JSON's top level
    can legally be an array, string, number, or ``null`` -- rejected
    here with a ``WARNING:`` so every caller can rely on this function's
    declared ``dict[str, Any] | None`` return type without its own
    defensive `isinstance` check.

    See :data:`_LOCK_FILE_CACHE` for the memoization this and
    :func:`load_lock_toml` share.
    """
    cache_key = _lock_file_cache_key(lock_path)
    if cache_key is not None:
        cached = _LOCK_FILE_CACHE.get(cache_key)
        if cached is not None:
            return cached
    try:
        with open(lock_path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        # Invalid UTF-8 bytes raise a bare UnicodeDecodeError from the
        # text-mode read itself, not json.JSONDecodeError -- still just
        # a malformed/unparseable file, not a reason to abort the whole
        # cascade.
        log.warning("Failed to parse %s: %s", lock_path, exc)
        return None
    if not isinstance(data, dict):
        log.warning(
            "%s: top-level JSON value is %s, expected an object",
            lock_path,
            type(data).__name__,
        )
        return None
    if cache_key is not None:
        _LOCK_FILE_CACHE[cache_key] = data
    return data


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
    return isinstance(table, dict) and isinstance(table.get(required_key), value_type)


def index_packages_by_name(
    packages: Iterable[object],
    key: Callable[[str], str] = str,
) -> dict[str, list[dict[str, Any]]]:
    """Group every well-formed entry of *packages* (a lock format's flat
    ``[[package]]``-style list) by its ``name`` field (passed through
    *key*, e.g. :func:`packaging.utils.canonicalize_name` when a caller
    needs PEP 503-canonicalized grouping instead of the literal name),
    preserving file order both across and within names.

    A non-table entry, or a table with a missing/non-string/empty
    ``name``, is silently excluded -- it can never be the target of a
    real dependency reference by name, so it's inert here; the caller
    validating that same list for other purposes (e.g. resolving a
    specific referenced name) is where a malformed entry actually
    matters and gets its own ``WARNING:``.

    Used to detect a name that resolves to more than one distinct
    version within one lock file -- ambiguous without evaluating
    markers/extras against a real environment, which no extractor using
    this helper does; the caller decides whether to skip such a name
    or (when every entry agrees on the same version, e.g. PDM's
    per-extra duplicate records) treat it as unambiguous after all.
    """
    by_name: dict[str, list[dict[str, Any]]] = {}
    for pkg in packages:
        if not isinstance(pkg, dict):
            continue
        name = pkg.get("name")
        if isinstance(name, str) and name:
            by_name.setdefault(key(name), []).append(pkg)
    return by_name


def version_key(version: str) -> Version | str:
    """Return a hashable key for *version* that compares equal under PEP 440
    equivalences (e.g. ``"1.0" == "1.0.0"``), falling back to the raw string
    when it does not parse as a PEP 440 version."""
    try:
        return Version(version)
    except (InvalidVersion, TypeError):
        return version


def index_packages_by_name_and_version(
    packages: Iterable[object],
) -> dict[tuple[str, Version | str], list[dict[str, Any]]]:
    """Group every well-formed ``[[package]]``-style entry by
    ``(canonicalize_name(name), version_key(version))``, preserving every entry
    seen for a given key -- multiple marker-branch entries can legitimately
    share the same resolved name and version, each contributing its own
    artifact set.

    Using :func:`version_key` ensures PEP 440 equivalences (e.g. ``"1.0"``
    and ``"1.0.0"`` across branches) index together into the same bucket,
    matching the pin extractor's own :func:`is_same_version` agreement.

    Shared by every hash-extraction companion module whose lock format's
    per-package entries are a flat table with a plain ``name``/``version``
    pair (:mod:`pitloom.extract._pylock_hashes`,
    :mod:`pitloom.extract._uv_lock_hashes`,
    :mod:`pitloom.extract._poetry_lock_hashes`,
    :mod:`pitloom.extract._pdm_lock_hashes`) -- factored out of four
    independently-drifting, byte-identical per-format copies.
    ``Pipfile.lock``'s own hash extractor indexes a differently-shaped
    ``{name: entry}`` mapping instead and doesn't use this helper.
    """
    index: dict[tuple[str, Version | str], list[dict[str, Any]]] = {}
    for pkg in packages:
        if not isinstance(pkg, dict):
            continue
        name, version = pkg.get("name"), pkg.get("version")
        if isinstance(name, str) and isinstance(version, str):
            key = (canonicalize_name(name), version_key(version))
            index.setdefault(key, []).append(pkg)
    return index


def sha256_file_entry_candidates(file_entries: object) -> list[tuple[str | None, str]]:
    """Return ``(file, sha256_digest)`` candidates from a ``[{file, hash},
    ...]``-shaped list -- the ``poetry.lock``/``pdm.lock`` per-package
    ``files`` shape. A ``hash`` value without a ``sha256:`` prefix (a
    different digest algorithm) is simply not a candidate, not an error.

    Shared by :mod:`pitloom.extract._poetry_lock_hashes` and
    :mod:`pitloom.extract._pdm_lock_hashes`, whose per-package ``files``
    entries share this exact shape -- factored out of two independently-
    drifting, byte-identical copies.
    """
    if not isinstance(file_entries, list):
        return []
    candidates: list[tuple[str | None, str]] = []
    for entry in file_entries:
        if not isinstance(entry, dict):
            continue
        raw_hash = entry.get("hash")
        if not isinstance(raw_hash, str) or not raw_hash.startswith("sha256:"):
            continue
        file_name = entry.get("file")
        candidates.append(
            (
                file_name if isinstance(file_name, str) else None,
                raw_hash.removeprefix("sha256:"),
            )
        )
    return candidates


def is_usable_version(version: object) -> TypeGuard[str]:
    """Return whether *version* is a non-empty string that parses as a
    valid PEP 440 version -- the "can this become a real
    ``name==version`` pin" check every lock/pin extractor applies to a
    ``[[package]]`` entry's ``version`` field before using it. Rejects
    not just non-strings but a syntactically-string-yet-not-a-version
    value too (whitespace, ``"*"``, ``"not a version"``) -- without this,
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
    if not isinstance(version, str) or not version:
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

    Generic over tuple arity so :func:`group_versions_by_canonical_name`'s
    ``(name, version)`` pairs, :func:`group_pin_triples_by_canonical_name`'s
    ``(name, operator, version)`` triples, and any other caller's own
    ``(name, ...)`` tuple shape share one implementation instead of a
    per-caller copy of the same loop -- public (no leading underscore)
    since :mod:`pitloom.assemble.spdx3._document_locked_deps` groups a
    third, differently-shaped ``(name, dep, pinned)`` triple that fits
    neither typed wrapper below.
    """
    by_canonical: dict[str, list[_CanonicalGroupT]] = {}
    for item in items:
        by_canonical.setdefault(canonicalize_name(item[0]), []).append(item)
    return by_canonical


def group_versions_by_canonical_name(
    pairs: Iterable[tuple[str, str]],
) -> dict[str, list[tuple[str, str]]]:
    """Group ``(name, version)`` pairs by PEP 503-canonicalized *name* --
    see :func:`group_by_canonical_name`.

    A caller decides what a multi-entry group means for its own format:
    :mod:`pitloom.extract._pdm_lock` collapses a group to one entry when
    every version agrees (its per-extra duplicate records always do) and
    skips just that name otherwise. See :func:`group_pin_triples_by_canonical_name`
    for the sibling used where the pin's operator (``==`` vs ``===``) also
    needs to survive grouping.
    """
    return group_by_canonical_name(pairs)


def group_pin_triples_by_canonical_name(
    triples: Iterable[tuple[str, str, str]],
) -> dict[str, list[tuple[str, str, str]]]:
    """Group ``(name, operator, version)`` pins by PEP 503-canonicalized
    *name* -- see :func:`group_by_canonical_name`. The ``===``-aware
    sibling of :func:`group_versions_by_canonical_name`, for
    :mod:`pitloom.extract._pipfile_lock` and
    :mod:`pitloom.extract._requirements_txt`, whose ``version`` field is
    already a PEP 440 specifier that can carry either exact-pin operator
    and must keep it through to the formatted ``name<op>version`` output.

    A caller decides what a multi-entry group means for its own format:
    :mod:`pitloom.extract._pipfile_lock` skips just the conflicting name
    and keeps the rest; :mod:`pitloom.extract._requirements_txt` treats
    any group with more than one distinct version as disqualifying its
    whole file, since it has no per-format definition of "expected
    duplication" the way an extra-variant lock entry does.
    """
    return group_by_canonical_name(triples)


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
    :mod:`pitloom.extract._pipfile_lock` and
    :mod:`pitloom.extract._requirements_txt` both need a raw-string
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


def canonical_name_and_pinned_version(dep: str) -> tuple[str, str] | None:
    """Parse an exact-pin dependency string -- one already known to carry a
    single exact pin, as every lock/pin extractor in this package formats
    its own output (e.g. ``f"{name}=={version}"``) -- back into
    ``(canonicalize_name(name), version)``, or ``None`` if it doesn't parse
    or isn't a single exact pin.

    Used by each format's hash-extraction companion
    (:mod:`pitloom.extract._pylock_hashes` and its siblings) to look a pin
    extractor's own already-resolved winning dependency back up in the raw
    lock data by name and version, so hash extraction never re-derives the
    pin extractor's own group/marker/non-registry-source filtering and
    conflicting-version exclusion a second time -- it only ever computes a
    hash for a package the pin extractor itself decided to include.
    """
    try:
        req = Requirement(dep)
    except (InvalidRequirement, TypeError):
        return None
    pin = single_exact_pin(req.specifier)
    if pin is None:
        return None
    _operator, version = pin
    return canonicalize_name(req.name), version


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
    non-table entry, or one with a missing/non-string ``name`` or
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
    if not isinstance(name, str) or not name:
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
