# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for PEP 751 ``pylock.toml`` SHA-256 digest extraction
(:mod:`pitloom.extract._pylock_hashes`).
"""

import tempfile
from pathlib import Path

from packaging.utils import canonicalize_name

from pitloom.extract._pylock import extract_pylock_dependencies
from pitloom.extract._pylock_hashes import extract_pylock_hashes

REAL_WORLD_LOCKS = (
    Path(__file__).parent.parent / "fixtures" / "real-world-locks" / "pylock"
)

#: annotated-types' wheel hash from
#: tests/fixtures/real-world-locks/pylock/snowflake-cli-3.26.0/pylock.toml --
#: its sdist hash differs, so this also confirms wheel-over-sdist preference.
_ANNOTATED_TYPES_WHEEL_HASH = (
    "1f02e8b43a8fbbc3f3e0d4f0f4bfc8131bcb4eebe8849b8e5c773f3a1c582a53"
)


def test_no_lock_file_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert extract_pylock_hashes(Path(tmp), []) is None


def test_real_world_snowflake_cli_annotated_types_wheel_hash() -> None:
    project_dir = REAL_WORLD_LOCKS / "snowflake-cli-3.26.0"
    deps = extract_pylock_dependencies(project_dir)
    assert deps is not None

    hashes = extract_pylock_hashes(project_dir, deps)
    assert hashes is not None
    assert hashes[canonicalize_name("annotated-types")] == _ANNOTATED_TYPES_WHEEL_HASH


def test_determinism_same_lock_same_hash() -> None:
    project_dir = REAL_WORLD_LOCKS / "snowflake-cli-3.26.0"
    deps = extract_pylock_dependencies(project_dir)
    assert deps is not None

    first = extract_pylock_hashes(project_dir, deps)
    second = extract_pylock_hashes(project_dir, deps)
    assert first == second


def test_missing_dependency_omitted_not_error() -> None:
    project_dir = REAL_WORLD_LOCKS / "snowflake-cli-3.26.0"
    hashes = extract_pylock_hashes(project_dir, ["nonexistent-package==1.0"])
    assert hashes == {}
