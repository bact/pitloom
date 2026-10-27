# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SHA-256 digest extraction from a ``poetry.lock``, alongside
:mod:`pitloom.extract.lock.poetry`'s ``name==version`` pin extraction.

Split into its own module (rather than growing :mod:`pitloom.extract.lock.poetry`
further) purely for this repo's file-size discipline.

Takes the pin extractor's own already-resolved winning dependency strings
as input (never re-derives which packages qualify): this both avoids
duplicating :mod:`pitloom.extract.lock.poetry`'s group/optional/non-
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

from packaging.utils import (
    InvalidSdistFilename,
    InvalidWheelFilename,
    canonicalize_name,
    parse_sdist_filename,
    parse_wheel_filename,
)
from packaging.version import Version

from pitloom.core.pep440 import parse_version
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

__all__ = [
    "extract_poetry_lock_hashes",
    "normalize_distribution_name",
    "normalize_distribution_version",
]


def normalize_distribution_name(name: str) -> str:
    """Normalize a package distribution name per PEP 427 / PEP 625:
    canonicalize per PEP 503 (lowercasing, runs of ``[-_.]+`` replaced with
    a single hyphen), then replace all hyphens with underscores -- the form
    a wheel or sdist filename carries."""
    return canonicalize_name(name).replace("-", "_")


def normalize_distribution_version(version: str) -> str:
    """Normalize a version string for artifact filenames per PEP 427 / PEP 625:
    replace local version ``+`` with ``_``."""
    return version.replace("+", "_")


def _parse_wheel(filename: str) -> Version | None:
    try:
        _name, ver, _build, _tags = parse_wheel_filename(filename)
        return ver
    except (InvalidWheelFilename, ValueError):
        return None


def _parse_sdist(filename: str) -> Version | None:
    try:
        _name, ver = parse_sdist_filename(filename)
        return ver
    except (InvalidSdistFilename, ValueError):
        pass
    for ext in (".tar.bz2", ".tgz", ".tar.xz"):
        if filename.endswith(ext):
            normalized = filename[: -len(ext)] + ".tar.gz"
            try:
                _name, ver = parse_sdist_filename(normalized)
                return ver
            except (InvalidSdistFilename, ValueError):
                pass
    return None


def _parse_artifact_version(filename: str, expected_version: str) -> Version | None:
    """Attempt to parse a wheel or sdist version from *filename*, supporting
    historical sdist extensions (.tar.bz2, etc.) and PEP 427/625 local version
    '+' to '_' normalization."""
    if ver := _parse_wheel(filename):
        return ver
    if ver := _parse_sdist(filename):
        return ver

    if "+" in expected_version:
        normalized_ver = normalize_distribution_version(expected_version)
        if f"-{normalized_ver}-" in filename:
            candidate_fn = filename.replace(
                f"-{normalized_ver}-", f"-{expected_version}-"
            )
            if ver := _parse_wheel(candidate_fn):
                return ver
        for ext in (".tar.gz", ".zip", ".tar.bz2", ".tgz", ".tar.xz"):
            if filename.endswith(f"-{normalized_ver}{ext}"):
                prefix = filename[: -len(ext) - len(normalized_ver) - 1]
                candidate_fn = f"{prefix}-{expected_version}.tar.gz"
                if ver := _parse_sdist(candidate_fn):
                    return ver
    return None


def _filename_matches_version(
    filename: str | None,
    expected_version: str,
    canon_name: str | None = None,
) -> bool:
    """Return whether a wheel or sdist *filename* belongs to *expected_version*.

    When *canon_name* is given, the string fallback anchors the version
    match to the expected position (after the package-name prefix) to
    avoid false positives on filenames whose package name itself contains
    a version-like substring (e.g. ``lib-1.0-tools-2.0.tar.gz``).
    """
    if not isinstance(filename, str):
        return False
    target_ver = parse_version(expected_version)
    if target_ver is not None:
        parsed_ver = _parse_artifact_version(filename, expected_version)
        if parsed_ver is not None:
            return parsed_ver == target_ver
    # Fallback: plain substring match for non-PEP-440 or unparseable
    # filenames. When canon_name is available, anchor after the
    # normalized package name prefix to avoid matching version-like
    # substrings inside the package name itself.
    lower_expected = expected_version.lower()
    lower_normalized = normalize_distribution_version(lower_expected)
    lower_fn = filename.lower()
    if canon_name is not None:
        # PEP 427/625 filenames use the normalized (underscored) name;
        # pre-PEP 625 sdists often use the canonical name with hyphens
        # (e.g. pytest-cov-2.8.1.tar.gz) or dots.
        norm_name = normalize_distribution_name(canon_name)
        prefixes = (f"{norm_name}-", f"{canon_name.lower()}-")
        matched_prefix = next((p for p in prefixes if lower_fn.startswith(p)), None)
        if matched_prefix is None:
            return False
        suffix = lower_fn[len(matched_prefix) :]
        return (
            suffix.startswith(f"{lower_expected}-")
            or suffix.startswith(f"{lower_normalized}-")
            or any(
                suffix in (f"{lower_expected}{ext}", f"{lower_normalized}{ext}")
                for ext in (".tar.gz", ".zip", ".tar.bz2", ".tgz", ".tar.xz")
            )
        )
    return (
        f"-{lower_expected}-" in lower_fn
        or f"-{lower_normalized}-" in lower_fn
        or any(
            lower_fn.endswith(f"-{lower_expected}{ext}")
            or lower_fn.endswith(f"-{lower_normalized}{ext}")
            for ext in (".tar.gz", ".zip", ".tar.bz2", ".tgz", ".tar.xz")
        )
    )


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
    files_by_name: dict[str, list[object]] = {}
    for name, entries in files_table.items():
        if isinstance(name, str) and isinstance(entries, list):
            files_by_name.setdefault(canonicalize_name(name), []).extend(entries)
    return files_by_name


def extract_poetry_lock_hashes(
    project_dir: Path, locked_dependencies: list[str]
) -> dict[str, str] | None:
    """Read ``poetry.lock`` next to ``pyproject.toml`` and return a hex
    SHA-256 digest per PEP 503-canonicalized package name, for exactly the
    entries of *locked_dependencies* (the already-resolved output of
    :func:`pitloom.extract.lock.poetry.extract_poetry_lock_dependencies`
    for the same *project_dir*).

    Returns ``None`` when no ``poetry.lock`` is present or it can't be
    parsed. A dependency with no ``sha256``-prefixed hash on any of its
    file entries is simply omitted, not an error.
    """
    lock_path = project_dir / "poetry.lock"
    data = load_lock_toml(lock_path)
    if data is None:
        return None
    if not has_required_top_level_table(data, "metadata", "lock-version", str):
        return None

    packages = data.get("package", [])
    if not isinstance(packages, list):
        return None

    index = index_packages_by_name_and_version(packages)
    legacy_files_by_name = _legacy_metadata_files_by_canonical_name(data)

    def _lookup_candidates(
        canon_name: str, version: str
    ) -> list[tuple[str | None, str]]:
        candidates: list[tuple[str | None, str]] = []
        for pkg in index.get((canon_name, version_key(version)), []):
            candidates.extend(sha256_file_entry_candidates(pkg.get("files")))
        if not candidates:
            candidates = [
                c
                for c in sha256_file_entry_candidates(
                    legacy_files_by_name.get(canon_name)
                )
                if _filename_matches_version(c[0], version, canon_name=canon_name)
            ]
        return candidates

    return resolve_locked_hashes(locked_dependencies, _lookup_candidates)
