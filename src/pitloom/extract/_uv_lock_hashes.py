# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SHA-256 digest extraction from a ``uv.lock``, alongside
:mod:`pitloom.extract._uv_lock`'s ``name==version`` pin extraction.

Split into its own module (rather than growing :mod:`pitloom.extract._uv_lock`
further) purely for this repo's file-size discipline.

Takes the pin extractor's own already-resolved winning dependency strings
as input (never re-derives which packages qualify): this both avoids
duplicating :mod:`pitloom.extract._uv_lock`'s workspace-root
disambiguation and transitive-dependency-graph walk here, and sidesteps
having to reproduce it correctly a second time. A ``uv.lock``'s flat
``[[package]]`` table can legitimately list the same name at two
genuinely different versions (one per marker/Python-version branch) --
indexing by ``(name, version)`` together, not name alone, is what keeps
that from being ambiguous here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitloom.extract._hash_selection import select_sha256_hash
from pitloom.extract._lock_common import (
    canonical_name_and_pinned_version,
    index_packages_by_name_and_version,
    load_lock_toml,
)

__all__ = ["extract_uv_lock_hashes"]


def _artifact_hash_candidates(pkg: dict[str, Any]) -> list[tuple[str | None, str]]:
    """Return ``(url, sha256_digest)`` candidates for one ``[[package]]``
    entry's ``sdist`` table and each of its ``wheels`` entries. Each
    artifact's ``hash`` is a single ``"sha256:<hex>"`` string (unlike
    ``pylock.toml``'s multi-algorithm table) -- a non-sha256-prefixed
    value is simply not a candidate, not an error.
    """
    candidates: list[tuple[str | None, str]] = []
    for artifact in [pkg.get("sdist"), *(pkg.get("wheels") or [])]:
        if not isinstance(artifact, dict):
            continue
        raw_hash = artifact.get("hash")
        if not isinstance(raw_hash, str) or not raw_hash.startswith("sha256:"):
            continue
        url = artifact.get("url")
        candidates.append(
            (url if isinstance(url, str) else None, raw_hash.removeprefix("sha256:"))
        )
    return candidates


def extract_uv_lock_hashes(
    project_dir: Path, locked_dependencies: list[str]
) -> dict[str, str] | None:
    """Read ``uv.lock`` next to ``pyproject.toml`` and return a hex SHA-256
    digest per PEP 503-canonicalized package name, for exactly the entries
    of *locked_dependencies* (the already-resolved output of
    :func:`pitloom.extract._uv_lock.extract_uv_lock_dependencies` for the
    same *project_dir*).

    Returns ``None`` when no ``uv.lock`` is present, it can't be parsed,
    or it doesn't look genuine (missing the int ``version`` marker every
    real ``uv.lock`` has). A dependency with no ``sha256``-prefixed hash
    on any of its artifacts is simply omitted, not an error.
    """
    lock_path = project_dir / "uv.lock"
    data = load_lock_toml(lock_path)
    if data is None:
        return None
    if not isinstance(data.get("version"), int):
        return None

    packages = data.get("package", [])
    if not isinstance(packages, list):
        return None

    index = index_packages_by_name_and_version(packages)

    hashes: dict[str, str] = {}
    for dep in locked_dependencies:
        parsed = canonical_name_and_pinned_version(dep)
        if parsed is None:
            continue
        canon_name, version = parsed
        candidates = [
            candidate
            for pkg in index.get((canon_name, version), [])
            for candidate in _artifact_hash_candidates(pkg)
        ]
        digest = select_sha256_hash(candidates)
        if digest is not None:
            hashes[canon_name] = digest
    return hashes
