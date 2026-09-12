# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SHA-256 digest extraction from a ``poetry.lock``, alongside
:mod:`pitloom.extract._poetry_lock`'s ``name==version`` pin extraction.

Split into its own module (rather than growing :mod:`pitloom.extract._poetry_lock`
further) purely for this repo's file-size discipline.

Takes the pin extractor's own already-resolved winning dependency strings
as input (never re-derives which packages qualify): this both avoids
duplicating :mod:`pitloom.extract._poetry_lock`'s group/optional/non-
registry-source filtering here, and sidesteps having to reproduce it
correctly a second time.

Unlike every sibling lock format, a package's file hashes are **not**
always nested in its own ``[[package]]`` entry: Poetry 2.1+
(``lock-version`` 2.1+) writes them there directly as a per-package
``files`` array, but every earlier lock version (1.x) instead lists them
in one *separate*, top-level ``[metadata.files]`` table keyed by literal
package name. Both shapes are checked here -- the per-package ``files``
array first, falling back to ``metadata.files`` -- so this module works
across the whole range of lock files this repo's own fixtures cover
(``tests/fixtures/real-world-locks/poetry/``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from packaging.utils import canonicalize_name

from pitloom.extract._hash_selection import select_sha256_hash
from pitloom.extract._lock_common import (
    canonical_name_and_pinned_version,
    index_packages_by_name_and_version,
    load_lock_toml,
    sha256_file_entry_candidates,
)

__all__ = ["extract_poetry_lock_hashes"]


def _legacy_metadata_files_by_canonical_name(
    data: dict[str, Any],
) -> dict[str, list[object]]:
    """Index the top-level ``[metadata.files]`` table (Poetry lock-version
    1.x) by PEP 503-canonicalized package name -- absent entirely on a
    2.1+ lock, where every package's own ``files`` field is used instead.
    """
    metadata = data.get("metadata")
    files_table = metadata.get("files") if isinstance(metadata, dict) else None
    if not isinstance(files_table, dict):
        return {}
    return {
        canonicalize_name(name): entries
        for name, entries in files_table.items()
        if isinstance(name, str)
    }


def extract_poetry_lock_hashes(
    project_dir: Path, locked_dependencies: list[str]
) -> dict[str, str] | None:
    """Read ``poetry.lock`` next to ``pyproject.toml`` and return a hex
    SHA-256 digest per PEP 503-canonicalized package name, for exactly the
    entries of *locked_dependencies* (the already-resolved output of
    :func:`pitloom.extract._poetry_lock.extract_poetry_lock_dependencies`
    for the same *project_dir*).

    Returns ``None`` when no ``poetry.lock`` is present or it can't be
    parsed. A dependency with no ``sha256``-prefixed hash on any of its
    file entries is simply omitted, not an error.
    """
    lock_path = project_dir / "poetry.lock"
    data = load_lock_toml(lock_path)
    if data is None:
        return None

    packages = data.get("package", [])
    if not isinstance(packages, list):
        return None

    index = index_packages_by_name_and_version(packages)
    legacy_files_by_name = _legacy_metadata_files_by_canonical_name(data)

    hashes: dict[str, str] = {}
    for dep in locked_dependencies:
        parsed = canonical_name_and_pinned_version(dep)
        if parsed is None:
            continue
        canon_name, version = parsed
        candidates: list[tuple[str | None, str]] = []
        for pkg in index.get((canon_name, version), []):
            candidates.extend(sha256_file_entry_candidates(pkg.get("files")))
        if not candidates:
            candidates = sha256_file_entry_candidates(
                legacy_files_by_name.get(canon_name)
            )
        digest = select_sha256_hash(candidates)
        if digest is not None:
            hashes[canon_name] = digest
    return hashes
