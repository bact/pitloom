# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SHA-256 digest extraction from a Pipenv ``Pipfile.lock``, alongside
:mod:`pitloom.extract.lock.pipfile`'s ``name<op>version`` pin extraction.

Split into its own module (rather than growing
:mod:`pitloom.extract.lock.pipfile` further) purely for this repo's
file-size discipline.

Takes the pin extractor's own already-resolved winning dependency strings
as input (never re-derives which packages qualify): this both avoids
duplicating :mod:`pitloom.extract.lock.pipfile`'s non-registry-source
filtering here, and sidesteps having to reproduce it correctly a second
time.

Unlike every sibling lock format, ``Pipfile.lock``'s per-package
``hashes`` list carries no filename at all -- just a flat list of
``"sha256:<hex>"`` strings, one per distributed artifact (wheel and
sdist alike). :func:`~pitloom.extract.lock._hash_selection.select_sha256_hash`
therefore has no way to identify (let alone prefer) a wheel here; its
filename-less fallback -- sort the raw digests themselves -- is what
actually runs for this format, and the artifact it picks is arbitrary by
construction, not wheel-preferring the way it is for every other format.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from packaging.specifiers import InvalidSpecifier
from packaging.utils import canonicalize_name

from pitloom.core.pep440 import parse_specifier_set
from pitloom.extract.lock._hash import resolve_locked_hashes
from pitloom.extract.lock.common import (
    has_required_top_level_table,
    load_lock_json,
    single_exact_pin,
    version_key,
)

__all__ = ["extract_pipfile_lock_hashes"]


def _hash_candidates(hashes: object) -> list[tuple[str | None, str]]:
    """Return ``(None, sha256_digest)`` candidates from a Pipfile.lock
    per-package ``hashes`` list -- no filename is ever available for this
    format. A hash string without a ``sha256:`` prefix (a different
    digest algorithm) is simply not a candidate, not an error.
    """
    if not isinstance(hashes, list):
        return []
    return [
        (None, entry.removeprefix("sha256:"))
        for entry in hashes
        if isinstance(entry, str) and entry.startswith("sha256:")
    ]


def _entry_pinned_version(entry: dict[str, Any]) -> str | None:
    """Return the exact pinned version from one Pipfile.lock entry's own
    ``version`` specifier string (e.g. ``"==2.31.0"``), or ``None`` when
    it isn't a single exact pin."""
    raw_version = entry.get("version")
    if not isinstance(raw_version, str):
        return None
    try:
        specifier_set = parse_specifier_set(raw_version)
    except InvalidSpecifier:
        return None
    pin = single_exact_pin(specifier_set)
    return pin[1] if pin is not None else None


def _index_by_name_and_version(
    section: dict[str, Any],
) -> dict[tuple[str, Any], list[dict[str, Any]]]:
    """Group every well-formed ``"default"``-section entry by
    ``(canonicalize_name(name), version_key(version))``."""
    index: dict[tuple[str, Any], list[dict[str, Any]]] = {}
    for name, entry in section.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            continue
        version = _entry_pinned_version(entry)
        if version is not None:
            key = (canonicalize_name(name), version_key(version))
            index.setdefault(key, []).append(entry)
    return index


def extract_pipfile_lock_hashes(
    project_dir: Path, locked_dependencies: list[str]
) -> dict[str, str] | None:
    """Read ``Pipfile.lock`` next to ``Pipfile``/``setup.py`` and return a
    hex SHA-256 digest per PEP 503-canonicalized package name, for
    exactly the entries of *locked_dependencies* (the already-resolved
    output of
    :func:`pitloom.extract.lock.pipfile.extract_pipfile_lock_dependencies`
    for the same *project_dir*).

    Returns ``None`` when no ``Pipfile.lock`` is present or it can't be
    parsed. A dependency with no ``sha256:``-prefixed hash in its
    ``hashes`` list is simply omitted, not an error.
    """
    lock_path = project_dir / "Pipfile.lock"
    data = load_lock_json(lock_path)
    if data is None:
        return None
    if not has_required_top_level_table(data, "_meta", "pipfile-spec", int):
        return None

    default_section = data.get("default", {})
    if not isinstance(default_section, dict):
        return None

    index = _index_by_name_and_version(default_section)

    return resolve_locked_hashes(
        locked_dependencies,
        lambda name, ver: (
            candidate
            for entry in index.get((name, version_key(ver)), [])
            for candidate in _hash_candidates(entry.get("hashes"))
        ),
    )
