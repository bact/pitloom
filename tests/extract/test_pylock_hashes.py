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
from pitloom.extract._pylock_hashes import (
    _artifact_hash_candidates,
    extract_pylock_hashes,
)

REAL_WORLD_LOCKS = (
    Path(__file__).parent.parent / "fixtures" / "real-world-locks" / "pylock"
)


def _write_lock(tmp_dir: Path, body: str) -> None:
    (tmp_dir / "pylock.toml").write_text(
        f'lock-version = "1.0"\ncreated-by = "test"\n{body}', encoding="utf-8"
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


def test_invalid_top_level_keys_returns_none() -> None:
    """`_extract_validated_packages()` rejects a `pylock.toml` missing its
    required top-level keys -- hash extraction must fail the same way as
    pin extraction."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pylock.toml").write_text(
            'lock-version = "1.0"\n', encoding="utf-8"
        )  # missing 'created-by'
        assert extract_pylock_hashes(tmp_path, []) is None


def test_locked_dependency_not_a_single_exact_pin_skipped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[packages]]\nname = "requests"\nversion = "2.31.0"\n'
            'wheels = [{ url = "requests-2.31.0.whl", '
            'hashes = { sha256 = "' + "a" * 64 + '" } }]\n',
        )
        hashes = extract_pylock_hashes(tmp_path, ["requests>=2.0"])
        assert hashes == {}


def test_artifact_hash_candidates_skips_malformed_artifacts() -> None:
    assert not _artifact_hash_candidates({"sdist": "not-a-dict", "wheels": []})
    assert not _artifact_hash_candidates(
        {"sdist": {"url": "pkg.tar.gz", "hashes": "not-a-dict"}, "wheels": []}
    )
    assert not _artifact_hash_candidates(
        {
            "sdist": {"url": "pkg.tar.gz", "hashes": {"blake2b": "notsha256"}},
            "wheels": [],
        }
    )
    assert _artifact_hash_candidates(
        {
            "sdist": None,
            "wheels": [
                {"url": "pkg.whl", "hashes": {"sha256": "b" * 64}},
            ],
        }
    ) == [("pkg.whl", "b" * 64)]
