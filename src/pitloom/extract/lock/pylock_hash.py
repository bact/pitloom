# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SHA-256 digest extraction from a PEP 751 ``pylock.toml``, alongside
:mod:`pitloom.extract.lock.pylock`'s ``name==version`` pin extraction.

Split into its own module (rather than growing :mod:`pitloom.extract.lock.pylock`
further) purely for this repo's file-size discipline.

Takes the pin extractor's own already-resolved winning dependency strings
as input (never re-derives which packages qualify): this both avoids
duplicating :mod:`pitloom.extract.lock.pylock`'s group/marker/non-registry-
source filtering and conflicting-version exclusion here, and sidesteps
having to reproduce it correctly a second time.
"""

from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import Any

from pitloom.extract._extract_utils import filename_from_url
from pitloom.extract.lock._hash import (
    index_packages_by_name_and_version,
    package_artifacts,
    resolve_locked_hashes,
)
from pitloom.extract.lock.common import (
    load_lock_toml,
    version_key,
)

__all__ = ["extract_pylock_hashes"]


def _artifact_hash_candidates(pkg: dict[str, Any]) -> list[tuple[str | None, str]]:
    """Return ``(filename, sha256_digest)`` candidates for one
    ``[[packages]]`` entry's ``sdist`` table and each of its ``wheels`` entries
    -- each independently a PEP 751 ``hashes`` table keyed by algorithm name, so
    an artifact lacking a ``sha256`` key (only some other algorithm) is
    simply not a candidate, not an error; a sibling artifact on the same
    package may still have one.
    """
    candidates: list[tuple[str | None, str]] = []
    for artifact in package_artifacts(pkg):
        hashes = artifact.get("hashes")
        if not isinstance(hashes, dict):
            continue
        digest = hashes.get("sha256")
        if not isinstance(digest, str):
            continue
        raw_name = artifact.get("name")
        raw_url = artifact.get("url")
        raw_path = artifact.get("path")
        filename: str | None
        if isinstance(raw_name, str) and raw_name:
            # PEP 751 artifact `name` field could theoretically contain
            # query/fragment chars; strip them defensively.
            filename = raw_name.split("?", 1)[0].split("#", 1)[0] or None
        elif isinstance(raw_url, str) and raw_url:
            filename = filename_from_url(raw_url)
        elif isinstance(raw_path, str) and raw_path:
            filename = PureWindowsPath(raw_path).name or None
        else:
            filename = None
        candidates.append((filename, digest))
    return candidates


def extract_pylock_hashes(
    project_dir: Path, locked_dependencies: list[str]
) -> dict[str, str] | None:
    """Read ``pylock.toml`` next to ``pyproject.toml`` and return a hex
    SHA-256 digest per PEP 503-canonicalized package name, for exactly the
    entries of *locked_dependencies* (the already-resolved output of
    :func:`pitloom.extract.lock.pylock.extract_pylock_dependencies` for the
    same *project_dir*).

    Returns ``None`` when no ``pylock.toml`` is present or it can't be
    parsed. A dependency with no ``sha256`` entry on any of its artifacts
    (only some other PEP 751 hash algorithm) is simply omitted, not an
    error -- absent source data, not a deviation.
    """
    lock_path = project_dir / "pylock.toml"
    data = load_lock_toml(lock_path)
    if data is None:
        return None

    if not isinstance(data.get("lock-version"), str):
        return None

    packages = data.get("packages")
    if not isinstance(packages, list):
        return None

    index = index_packages_by_name_and_version(packages)

    return resolve_locked_hashes(
        locked_dependencies,
        lambda name, ver: (
            candidate
            for pkg in index.get((name, version_key(ver)), [])
            for candidate in _artifact_hash_candidates(pkg)
        ),
    )
