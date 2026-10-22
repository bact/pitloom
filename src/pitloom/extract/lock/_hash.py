# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for lockfile SHA-256 digest extraction.

Consolidates candidate-artifact extraction, indexing, and deterministic
hash resolution across every per-format hash extractor companion
(:mod:`pitloom.extract.lock.poetry_hash`,
:mod:`pitloom.extract.lock.pdm_hash`,
:mod:`pitloom.extract.lock.uv_hash`,
:mod:`pitloom.extract.lock.pylock_hash`, and
:mod:`pitloom.extract.lock.pipfile_hash`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from packaging.utils import canonicalize_name
from packaging.version import Version

from pitloom.extract.lock._hash_selection import select_sha256_hash
from pitloom.extract.lock.common import (
    canonical_name_and_pinned_version,
    version_key,
)

__all__ = [
    "index_packages_by_name_and_version",
    "package_artifacts",
    "resolve_locked_hashes",
    "sha256_file_entry_candidates",
]


def index_packages_by_name_and_version(
    packages: Iterable[object],
) -> dict[tuple[str, Version | str], list[dict[str, Any]]]:
    """Group every well-formed ``[[package]]``-style entry by
    ``(canonicalize_name(name), version_key(version))``, preserving every entry
    seen for a given key -- multiple marker-branch entries can legitimately
    share the same resolved name and version, each contributing its own
    artifact set.

    Using :func:`~pitloom.extract.lock.common.version_key` ensures PEP 440
    equivalences (e.g. ``"1.0"`` and ``"1.0.0"`` across branches) index
    together into the same bucket, matching the pin extractor's own
    :func:`~pitloom.extract.lock.common.is_same_version` agreement.
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


def package_artifacts(pkg: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return a flat list of artifact tables from a package dictionary
    containing optional ``sdist`` (table) and ``wheels`` (list of tables)
    keys -- shared by ``uv.lock`` and PEP 751 ``pylock.toml`` artifact
    structures.
    """
    artifacts: list[dict[str, Any]] = []
    sdist = pkg.get("sdist")
    if isinstance(sdist, dict):
        artifacts.append(sdist)
    wheels = pkg.get("wheels")
    if isinstance(wheels, list):
        artifacts.extend(a for a in wheels if isinstance(a, dict))
    return artifacts


def resolve_locked_hashes(
    locked_dependencies: Iterable[str],
    candidate_lookup: Callable[[str, str], Iterable[tuple[str | None, str]]],
) -> dict[str, str]:
    """Resolve a hex SHA-256 digest per canonicalized package name for each
    exact-pin dependency in *locked_dependencies*.

    Calls *candidate_lookup(canon_name, version)* to retrieve candidate
    ``(filename, digest)`` pairs, and selects the winning digest via
    :func:`~pitloom.extract.lock._hash_selection.select_sha256_hash`. A dependency
    with no selectable candidate is omitted from the return mapping.
    """
    hashes: dict[str, str] = {}
    for dep in locked_dependencies:
        parsed = canonical_name_and_pinned_version(dep)
        if parsed is None:
            continue
        canon_name, version = parsed
        candidates = list(candidate_lookup(canon_name, version))
        digest = select_sha256_hash(candidates)
        if digest is not None:
            hashes[canon_name] = digest
    return hashes
