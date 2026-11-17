# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared ``WARNING:`` message helpers for lock/pin file extractors.

Every extractor's own malformed-entry/non-registry-source/missing-field
warning is said identically by routing through one of these instead of
hand-rolling a similarly-worded message per format -- see AGENTS.md's
"Recurring bug patterns" for why wording drift across siblings is worth
avoiding. Each one says a catalogued line of
:mod:`pitloom.messages.lock_files`, the lock named by its file name. Every
name here is re-exported from :mod:`pitloom.extract.lock.common`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pitloom.messages.lock_files import (
    FORMAT_MARKER_LINE,
    NAME_LINE,
    NOT_TABLE_LINE,
    SOURCE_LINE,
    TOP_KEY_LIST_LINE,
    TOP_KEY_TABLE_LINE,
    VERSION_LINE,
    VERSIONS_LINE,
    Said,
    say_lock_entry,
    say_lock_file,
)

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
    lock_file: str | Path,
    name: str,
    conflicting_versions: Iterable[str],
    *,
    said: Said | None = None,
) -> None:
    """Log the standard ``WARNING:`` (``lock-entry-conflict``) when multiple
    variants of the package *name* disagree on version in *lock_file*; the
    versions are listed as dropped. *said*: a per-run memo, a package
    reached twice in one walk is said once."""
    say_lock_entry(
        log,
        VERSIONS_LINE,
        file=lock_file,
        said=said,
        package=name,
        dropped=frozenset(conflicting_versions),
    )


def warn_not_genuine_lock_file(lock_path: Path, lock_key: str) -> None:
    """Log the standard ``WARNING:`` (``lock-file-wrong-format``) when a lock
    file lacks the top-level format marker *lock_key* (a dotted key such as
    ``metadata.lock-version``): not a lock of the format its name says."""
    say_lock_file(log, FORMAT_MARKER_LINE, file=lock_path, lock_key=lock_key)


def warn_non_registry_source(
    lock_file: str, name: str, source_key: str, said: Said | None = None
) -> None:
    """Log the standard ``WARNING:`` for a non-registry-sourced entry
    (VCS, local path, archive/URL -- anything a bare ``name==version``
    pin can't represent), naming *lock_file* (e.g. ``"uv.lock"``),
    *name* (the package), and *source_key* (which non-registry marker
    was found). Shared by every extractor that has a non-registry-source
    concept (`poetry.py`, `pylock.py`, `uv.py`, `pdm.py`, `pipfile.py`)
    so the wording stays identical across formats.
    """
    say_lock_entry(
        log,
        SOURCE_LINE,
        file=lock_file,
        package=name,
        source_kind=source_key,
        said=said,
    )


def warn_top_level_key_wrong_type(
    lock_path: Path,
    lock_key: str,
    value: object,
    expected: Literal["list", "table"],
) -> None:
    """Log the shared ``WARNING:`` for a top-level lock-file key of the wrong
    shape (a ``packages``/``package`` key that isn't a list, a ``default``
    key that isn't a table): *value* is the value read, *expected* the shape
    the key has. Shared across formats the same way
    :func:`warn_non_registry_source` is shared for the non-registry-source
    case.
    """
    shape = TOP_KEY_LIST_LINE if expected == "list" else TOP_KEY_TABLE_LINE
    say_lock_file(log, shape, file=lock_path, lock_key=lock_key, value_type=value)


def warn_missing_version(lock_file: str, name: str, said: Said | None = None) -> None:
    """Log the shared ``WARNING:`` for an entry whose ``version`` is missing
    or not a string -- identical across every format that validates its
    ``version`` field via
    :func:`pitloom.extract.lock.common.is_usable_version`."""
    say_lock_entry(log, VERSION_LINE, file=lock_file, package=name, said=said)


def warn_malformed_entry_not_table(
    lock_file: str, lock_key: str, value: object
) -> None:
    """Log the shared ``WARNING:`` for an entry of the list *lock_key*
    (``package``, ``packages``) that isn't a table -- shared across every
    format with this malformed-entry shape."""
    say_lock_entry(
        log, NOT_TABLE_LINE, file=lock_file, lock_key=lock_key, value_type=value
    )


def warn_missing_name(lock_file: str, lock_key: str, name: object) -> None:
    """Log the shared ``WARNING:`` for an entry of *lock_key* whose name is
    missing, not a string or no valid distribution name. *name* is
    untrusted: written cut and escaped."""
    say_lock_entry(log, NAME_LINE, file=lock_file, lock_key=lock_key, lock_value=name)
