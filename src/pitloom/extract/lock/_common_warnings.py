# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared ``WARNING:`` message helpers for lock/pin file extractors.

Every extractor's own malformed-entry/non-registry-source/missing-field
warning is worded identically by routing through one of these instead of
hand-rolling a similarly-worded message per format -- see AGENTS.md's
"Recurring bug patterns" for why wording drift across siblings is worth
avoiding. Every name here is re-exported from
:mod:`pitloom.extract.lock.common`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from pitloom.extract._extract_utils import quote_source
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

__all__ = [
    "warn_conflicting_versions",
    "warn_malformed_entry_not_table",
    "warn_missing_name",
    "warn_missing_version",
    "warn_non_registry_source",
    "warn_not_genuine_lock_file",
    "warn_top_level_key_wrong_type",
]


def warn_conflicting_versions(
    lock_file: str, name: str, conflicting_versions: Iterable[str]
) -> None:
    """Log the standard ``WARNING:`` when multiple variants of a package disagree
    on version in a lock file."""
    log.warning(
        "Skipping %s entry %r: pinned to conflicting versions (%s)",
        loggable(lock_file),
        name,
        loggable(", ".join(sorted(conflicting_versions))),
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
        quote_source(lock_path),
        table_key,
        container_type,
        required_key,
        loggable(lock_file),
    )


def warn_non_registry_source(lock_file: str, name: str, source_key: str) -> None:
    """Log the standard ``WARNING:`` for a non-registry-sourced entry
    (VCS, local path, archive/URL -- anything a bare ``name==version``
    pin can't represent), naming *lock_file* (e.g. ``"uv.lock"``),
    *name* (the package), and *source_key* (which non-registry marker
    was found). Shared by every extractor that has a non-registry-source
    concept (`poetry.py`, `pylock.py`, `uv.py`, `pdm.py`, `pipfile.py`)
    so the wording stays identical across formats.
    """
    log.warning(
        "Skipping %s entry %r: %s-sourced dependencies cannot be "
        "represented as a PEP 508 specifier",
        loggable(lock_file),
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
        quote_source(lock_path),
        key,
        type(value).__name__,
        expected,
        loggable(lock_file),
    )


def warn_missing_version(lock_file: str, name: str) -> None:
    """Log the shared ``"Skipping <lock file> entry '<name>': missing or
    non-string 'version'"`` warning -- identical across every format
    that validates its ``version`` field via
    :func:`pitloom.extract.lock.common.is_usable_version`."""
    log.warning(
        "Skipping %s entry %r: missing or non-string 'version'",
        loggable(lock_file),
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
        loggable(lock_file),
        entry_label,
        type(value).__name__,
    )


def warn_missing_name(context: str, name: object) -> None:
    """Log the shared ``"<context>: missing or non-string 'name'
    (name=<name>)"`` warning tail -- or, for a non-empty string that is no
    PEP 508 name, ``"invalid 'name'"`` -- *context* supplies each call
    site's own lead-in (which format, which kind of entry) since that part
    genuinely differs per site, while the recurring wording itself
    doesn't. *name* is untrusted: shown escaped."""
    problem = "invalid" if isinstance(name, str) and name else "missing or non-string"
    log.warning("%s: %s 'name' (name=%s)", context, problem, loggable(repr(name)))
