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
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, TypeGuard

from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from pitloom.extract._toml_io import TOMLDecodeError, load_toml_file

log = logging.getLogger(__name__)

__all__ = [
    "POETRY_LOCK_SOURCE_NAME",
    "find_first_present_key",
    "group_versions_by_canonical_name",
    "index_packages_by_name",
    "is_usable_version",
    "load_lock_json",
    "load_lock_toml",
    "single_exact_pin",
    "warn_malformed_entry_not_table",
    "warn_missing_name",
    "warn_missing_version",
    "warn_non_registry_source",
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


def load_lock_toml(lock_path: Path) -> dict[str, Any] | None:
    """Load *lock_path* as TOML, returning ``None`` (after a
    ``WARNING:`` for a parse/read failure, silently for a simply-absent
    file) instead of raising -- every lock format is optional
    enrichment, never a requirement, so a caller's usual next step is
    ``if data is None: return []``.
    """
    try:
        return load_toml_file(lock_path)
    except FileNotFoundError:
        return None
    except (OSError, TOMLDecodeError) as exc:
        log.warning("Failed to parse %s: %s", lock_path, exc)
        return None


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
    """
    try:
        with open(lock_path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Failed to parse %s: %s", lock_path, exc)
        return None
    if not isinstance(data, dict):
        log.warning(
            "%s: top-level JSON value is %s, expected an object",
            lock_path,
            type(data).__name__,
        )
        return None
    return data


def index_packages_by_name(
    packages: Iterable[object],
) -> dict[str, list[dict[str, Any]]]:
    """Group every well-formed entry of *packages* (a lock format's flat
    ``[[package]]``-style list) by its ``name`` field, preserving file
    order both across and within names.

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
            by_name.setdefault(name, []).append(pkg)
    return by_name


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


def group_versions_by_canonical_name(
    pairs: Iterable[tuple[str, str]],
) -> dict[str, list[tuple[str, str]]]:
    """Group ``(name, version)`` pairs by PEP 503-canonicalized *name*,
    preserving each pair's original literal name/version and file order
    both across and within groups.

    Comparing canonicalized (lowercased, ``-``/``_``/``.``-folded) names
    is required, not optional: ``Flask==1.0`` and ``flask==2.0`` name the
    same PyPI package under PEP 503, so a caller checking "does this name
    resolve to more than one version" must group them together or the
    check silently never fires for a mixed-case duplicate.

    A caller decides what a multi-entry group means for its own format:
    :mod:`pitloom.extract._pdm_lock` collapses a group to one entry when
    every version agrees (its per-extra duplicate records always do) and
    skips just that name otherwise; :mod:`pitloom.extract._requirements_txt`
    treats any group with more than one distinct version as disqualifying
    its whole file, since it has no per-format definition of "expected
    duplication" the way an extra-variant lock entry does.
    """
    by_canonical: dict[str, list[tuple[str, str]]] = {}
    for name, version in pairs:
        by_canonical.setdefault(canonicalize_name(name), []).append((name, version))
    return by_canonical


def single_exact_pin(specifier_set: SpecifierSet) -> str | None:
    """Return the bare version when *specifier_set* contains exactly one
    non-wildcard ``==`` specifier (e.g. ``SpecifierSet("==2.31.0")`` ->
    ``"2.31.0"``), or ``None`` for anything looser than one exact pin --
    a range, more than one specifier, or a prefix-match wildcard like
    ``"==2.31.*"`` (``packaging.specifiers.Specifier`` reports that as
    operator ``"=="`` too, but it pins a *range* of versions, not one
    exact release).

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
        or specifiers[0].operator != "=="
        or "*" in specifiers[0].version
    ):
        return None
    return specifiers[0].version


def warn_non_registry_source(lock_file: str, name: str, source_key: str) -> None:
    """Log the standard ``WARNING:`` for a non-registry-sourced entry
    (VCS, local path, archive/URL -- anything a bare ``name==version``
    pin can't represent), naming *lock_file* (e.g. ``"uv.lock"``),
    *name* (the package), and *source_key* (which non-registry marker
    was found). Shared by every extractor that has a non-registry-source
    concept (`_poetry_lock.py`, `_pylock.py`, `_uv_lock.py`,
    `_pdm_lock.py`, `_pipfile_lock.py`) so the wording stays identical
    across formats.
    """
    log.warning(
        "Skipping %s entry %r: %s-sourced dependencies cannot be "
        "represented as a PEP 508 specifier",
        lock_file,
        name,
        source_key,
    )


def warn_top_level_key_wrong_type(
    lock_path: Path, key: str, value: object, expected: str, lock_file: str
) -> None:
    """Log the shared ``"<path>: top-level '<key>' key is <type>,
    expected <shape> -- ignoring <lock file>"`` warning for a top-level
    lock-file key of the wrong shape (a ``packages``/``package`` key
    that isn't a list, a ``default`` key that isn't a table) -- shared
    across formats the same way :func:`warn_non_registry_source` is
    shared for the non-registry-source case.
    """
    log.warning(
        "%s: top-level '%s' key is %s, expected %s -- ignoring %s",
        lock_path,
        key,
        type(value).__name__,
        expected,
        lock_file,
    )


def warn_missing_version(lock_file: str, name: str) -> None:
    """Log the shared ``"Skipping <lock file> entry '<name>': missing or
    non-string 'version'"`` warning -- identical across every format
    that validates its ``version`` field via :func:`is_usable_version`."""
    log.warning(
        "Skipping %s entry %r: missing or non-string 'version'",
        lock_file,
        name,
    )


def warn_malformed_entry_not_table(
    lock_file: str, entry_label: str, value: object
) -> None:
    """Log the shared ``"Skipping malformed <lock file> <entry label>
    entry: expected a table, got <type>"`` warning for a top-level
    ``[[package]]``/``[[packages]]``-style entry that isn't a table --
    shared across every format with this malformed-entry shape."""
    log.warning(
        "Skipping malformed %s %s entry: expected a table, got %s",
        lock_file,
        entry_label,
        type(value).__name__,
    )


def warn_missing_name(context: str, name: object) -> None:
    """Log the shared ``"<context>: missing or non-string 'name'
    (name=<name>)"`` warning tail -- *context* supplies each call site's
    own lead-in (which format, which kind of entry) since that part
    genuinely differs per site, while the recurring "missing or
    non-string 'name'" wording itself doesn't."""
    log.warning("%s: missing or non-string 'name' (name=%r)", context, name)


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
