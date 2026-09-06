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
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, TypeGuard

from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from pitloom.extract._toml_io import TOMLDecodeError, load_toml_file

log = logging.getLogger(__name__)

__all__ = [
    "POETRY_LOCK_SOURCE_NAME",
    "default_group_included",
    "find_first_present_key",
    "group_versions_by_canonical_name",
    "has_required_top_level_table",
    "index_packages_by_name",
    "is_same_version",
    "is_usable_version",
    "load_lock_json",
    "load_lock_toml",
    "shape_validated_package",
    "single_exact_pin",
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
    except (OSError, TOMLDecodeError, UnicodeDecodeError) as exc:
        # tomllib/tomli's underlying decode step raises a bare
        # UnicodeDecodeError (not its own TOMLDecodeError) for invalid
        # UTF-8 bytes -- still just a malformed/unparseable file, not a
        # reason to abort the whole cascade.
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
    except InvalidVersion:
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


def warn_conflicting_versions(
    lock_file: str, name: str, conflicting_versions: Iterable[str]
) -> None:
    """Log the standard ``WARNING:`` when multiple variants of a package disagree
    on version in a lock file."""
    log.warning(
        "Skipping %s entry %r: pinned to conflicting versions (%s)",
        lock_file,
        name,
        ", ".join(sorted(conflicting_versions)),
    )


def warn_not_genuine_lock_file(
    lock_path: Path,
    table_key: str,
    required_key: str,
    lock_file: str,
    container_type: str = "table",
) -> None:
    """Log the standard ``WARNING:`` when a lock file lacks required top-level
    metadata."""
    log.warning(
        "%s: no top-level %r %s with a %r key -- "
        "doesn't look like a genuine %s, ignoring",
        lock_path,
        table_key,
        container_type,
        required_key,
        lock_file,
    )


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
