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

See also: :mod:`pitloom.extract.lock._common_warnings` (the shared
``WARNING:`` message helpers), :mod:`pitloom.extract.lock._lock_io`
(reading a lock file) and :mod:`pitloom.extract.lock._pins` (exact pins);
all three are re-exported below.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any, TypeGuard

from packaging.utils import InvalidName, canonicalize_name
from packaging.version import InvalidVersion, Version

from pitloom.extract.lock._common_warnings import (
    warn_conflicting_versions,
    warn_malformed_entry_not_table,
    warn_missing_name,
    warn_missing_version,
    warn_non_registry_source,
    warn_not_genuine_lock_file,
    warn_top_level_key_wrong_type,
)
from pitloom.extract.lock._lock_io import (
    LockFileRefusedError,
    load_lock_json,
    load_lock_toml,
    read_lock_bytes,
    warn_unreadable_lock_file,
)
from pitloom.extract.lock._pins import (
    canonical_name_and_pinned_version,
    group_by_canonical_name,
    is_same_version,
    parse_exact_pin_requirement,
    resolve_pinned_dependencies,
    single_exact_pin,
)

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
