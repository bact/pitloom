# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for lock/pin file extractors
(:mod:`pitloom.extract._poetry_lock`, :mod:`pitloom.extract._pylock`,
:mod:`pitloom.extract._uv_lock`, :mod:`pitloom.extract._pdm_lock`, and
future formats registered in
:mod:`pitloom.extract._locked_dependencies`).

Factored out once the same two steps -- "load the lock file, handling
absence/parse errors the same way every format does" and "group a
lock's flat package-entry list by name, to detect a name resolved to
more than one version" -- started being hand-copied into each new
extractor. Per this repo's "a pattern hand-copied across 3+ call sites
drifts" convention, this module is the one place both now live; only
extraction logic genuinely specific to one format (its own field names,
its own group/source-key conventions) stays in that format's own module.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from pitloom.extract._toml_io import TOMLDecodeError, load_toml_file

log = logging.getLogger(__name__)

__all__ = [
    "POETRY_LOCK_SOURCE_NAME",
    "find_first_present_key",
    "index_packages_by_name",
    "is_usable_version",
    "load_lock_toml",
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


def index_packages_by_name(packages: list[Any]) -> dict[str, list[dict[str, Any]]]:
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


def is_usable_version(version: Any) -> bool:
    """Return whether *version* is a non-empty string -- the "can this
    become a real ``name==version`` pin" check every lock/pin extractor
    (``poetry.lock``, ``pylock.toml``, ``uv.lock``, ``pdm.lock``) applies
    to a ``[[package]]`` entry's ``version`` field before using it.
    Factored out once four independent copies of ``not
    isinstance(version, str) or not version`` existed, per this repo's
    "a pattern hand-copied across 3+ call sites drifts" convention --
    each call site still logs its own ``WARNING:`` when this returns
    ``False``, since the message wording (which field, which format) is
    genuinely format-specific.
    """
    return isinstance(version, str) and bool(version)


def find_first_present_key(
    mapping: Mapping[str, Any], keys: Iterable[str]
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
