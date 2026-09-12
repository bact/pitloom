# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SHA-256 digest extraction from a ``pdm.lock``, alongside
:mod:`pitloom.extract._pdm_lock`'s ``name==version`` pin extraction.

Split into its own module (rather than growing :mod:`pitloom.extract._pdm_lock`
further) purely for this repo's file-size discipline.

Takes the pin extractor's own already-resolved winning dependency strings
as input (never re-derives which packages qualify): this both avoids
duplicating :mod:`pitloom.extract._pdm_lock`'s group/non-registry-source
filtering here, and sidesteps having to reproduce it correctly a second
time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from packaging.utils import canonicalize_name

from pitloom.extract._hash_selection import select_sha256_hash
from pitloom.extract._lock_common import canonical_name_and_pinned_version, load_lock_toml

__all__ = ["extract_pdm_lock_hashes"]


def _file_entry_candidates(file_entries: object) -> list[tuple[str | None, str]]:
    """Return ``(file, sha256_digest)`` candidates from a pdm.lock
    per-package ``files`` list (``[{file, hash}, ...]``). A ``hash``
    value without a ``sha256:`` prefix (a different digest algorithm) is
    simply not a candidate, not an error.
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


def _index_by_name_and_version(
    packages: list[object],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Group every well-formed ``[[package]]`` entry by
    ``(canonicalize_name(name), version)``."""
    index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for pkg in packages:
        if not isinstance(pkg, dict):
            continue
        name, version = pkg.get("name"), pkg.get("version")
        if isinstance(name, str) and isinstance(version, str):
            index.setdefault((canonicalize_name(name), version), []).append(pkg)
    return index


def extract_pdm_lock_hashes(
    project_dir: Path, locked_dependencies: list[str]
) -> dict[str, str] | None:
    """Read ``pdm.lock`` next to ``pyproject.toml`` and return a hex
    SHA-256 digest per PEP 503-canonicalized package name, for exactly the
    entries of *locked_dependencies* (the already-resolved output of
    :func:`pitloom.extract._pdm_lock.extract_pdm_lock_dependencies` for
    the same *project_dir*).

    Returns ``None`` when no ``pdm.lock`` is present or it can't be
    parsed. A dependency with no ``sha256``-prefixed hash on any of its
    file entries is simply omitted, not an error.
    """
    lock_path = project_dir / "pdm.lock"
    data = load_lock_toml(lock_path)
    if data is None:
        return None

    packages = data.get("package", [])
    if not isinstance(packages, list):
        return None

    index = _index_by_name_and_version(packages)

    hashes: dict[str, str] = {}
    for dep in locked_dependencies:
        parsed = canonical_name_and_pinned_version(dep)
        if parsed is None:
            continue
        canon_name, version = parsed
        candidates = [
            candidate
            for pkg in index.get((canon_name, version), [])
            for candidate in _file_entry_candidates(pkg.get("files"))
        ]
        digest = select_sha256_hash(candidates)
        if digest is not None:
            hashes[canon_name] = digest
    return hashes
