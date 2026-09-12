# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``pdm.lock`` SHA-256 digest extraction
(:mod:`pitloom.extract._pdm_lock_hashes`).
"""

import tempfile
from pathlib import Path

from packaging.utils import canonicalize_name

from pitloom.extract._pdm_lock import extract_pdm_lock_dependencies
from pitloom.extract._pdm_lock_hashes import extract_pdm_lock_hashes

REAL_WORLD_LOCKS = (
    Path(__file__).parent.parent / "fixtures" / "real-world-locks" / "pdm"
)

#: anyio's wheel hash from
#: tests/fixtures/real-world-locks/pdm/pdm-2.29.0/pdm.lock -- its sdist
#: hash differs, confirming wheel-over-sdist preference.
_ANYIO_WHEEL_HASH = "08b310f9e24a9594186fd75b4f73f4a4152069e3853f1ed8bfbf58369f4ad708"


def test_no_lock_file_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert extract_pdm_lock_hashes(Path(tmp), []) is None


def test_real_world_pdm_anyio_wheel_hash() -> None:
    project_dir = REAL_WORLD_LOCKS / "pdm-2.29.0"
    deps = extract_pdm_lock_dependencies(project_dir)
    assert deps is not None

    hashes = extract_pdm_lock_hashes(project_dir, deps)
    assert hashes is not None
    assert hashes[canonicalize_name("anyio")] == _ANYIO_WHEEL_HASH


def test_determinism_same_lock_same_hash() -> None:
    project_dir = REAL_WORLD_LOCKS / "pdm-2.29.0"
    deps = extract_pdm_lock_dependencies(project_dir)
    assert deps is not None

    first = extract_pdm_lock_hashes(project_dir, deps)
    second = extract_pdm_lock_hashes(project_dir, deps)
    assert first == second


def test_missing_dependency_omitted_not_error() -> None:
    project_dir = REAL_WORLD_LOCKS / "pdm-2.29.0"
    hashes = extract_pdm_lock_hashes(project_dir, ["nonexistent-package==1.0"])
    assert hashes == {}
