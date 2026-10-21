# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SHA-256 digest extraction from a ``pdm.lock``, alongside
:mod:`pitloom.extract.lock.pdm`'s ``name==version`` pin extraction.

Split into its own module (rather than growing :mod:`pitloom.extract.lock.pdm`
further) purely for this repo's file-size discipline.

Takes the pin extractor's own already-resolved winning dependency strings
as input (never re-derives which packages qualify): this both avoids
duplicating :mod:`pitloom.extract.lock.pdm`'s group/non-registry-source
filtering here, and sidesteps having to reproduce it correctly a second
time.
"""

from __future__ import annotations

from pathlib import Path

from pitloom.extract.lock._hash import (
    index_packages_by_name_and_version,
    resolve_locked_hashes,
    sha256_file_entry_candidates,
)
from pitloom.extract.lock.common import (
    has_required_top_level_table,
    load_lock_toml,
    version_key,
)

__all__ = ["extract_pdm_lock_hashes"]


def extract_pdm_lock_hashes(
    project_dir: Path, locked_dependencies: list[str]
) -> dict[str, str] | None:
    """Read ``pdm.lock`` next to ``pyproject.toml`` and return a hex
    SHA-256 digest per PEP 503-canonicalized package name, for exactly the
    entries of *locked_dependencies* (the already-resolved output of
    :func:`pitloom.extract.lock.pdm.extract_pdm_lock_dependencies` for
    the same *project_dir*).

    Returns ``None`` when no ``pdm.lock`` is present or it can't be
    parsed. A dependency with no ``sha256``-prefixed hash on any of its
    file entries is simply omitted, not an error.
    """
    lock_path = project_dir / "pdm.lock"
    data = load_lock_toml(lock_path)
    if data is None:
        return None
    if not has_required_top_level_table(data, "metadata", "lock_version", str):
        return None

    packages = data.get("package", [])
    if not isinstance(packages, list):
        return None

    index = index_packages_by_name_and_version(packages)

    return resolve_locked_hashes(
        locked_dependencies,
        lambda name, ver: (
            candidate
            for pkg in index.get((name, version_key(ver)), [])
            for candidate in sha256_file_entry_candidates(pkg.get("files"))
        ),
    )
