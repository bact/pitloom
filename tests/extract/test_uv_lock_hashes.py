# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``uv.lock`` SHA-256 digest extraction
(:mod:`pitloom.extract._uv_lock_hashes`).
"""

import tempfile
from pathlib import Path

from packaging.utils import canonicalize_name

from pitloom.extract._uv_lock import extract_uv_lock_dependencies
from pitloom.extract._uv_lock_hashes import (
    _artifact_hash_candidates,
    extract_uv_lock_hashes,
)

REAL_WORLD_LOCKS = Path(__file__).parent.parent / "fixtures" / "real-world-locks" / "uv"


def _write_lock(tmp_dir: Path, body: str) -> None:
    (tmp_dir / "uv.lock").write_text(f"version = 1\n{body}", encoding="utf-8")


#: jinja2's wheel hash from tests/fixtures/real-world-locks/uv/flask-3.1.3/uv.lock --
#: its sdist hash differs, so this also confirms wheel-over-sdist preference.
_JINJA2_WHEEL_HASH = "85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67"


def test_no_lock_file_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert extract_uv_lock_hashes(Path(tmp), []) is None


def test_real_world_flask_jinja2_wheel_hash() -> None:
    project_dir = REAL_WORLD_LOCKS / "flask-3.1.3"
    deps = extract_uv_lock_dependencies(project_dir, expected_name="Flask")
    assert deps is not None

    hashes = extract_uv_lock_hashes(project_dir, deps)
    assert hashes is not None
    assert hashes[canonicalize_name("jinja2")] == _JINJA2_WHEEL_HASH


def test_determinism_same_lock_same_hash() -> None:
    project_dir = REAL_WORLD_LOCKS / "flask-3.1.3"
    deps = extract_uv_lock_dependencies(project_dir, expected_name="Flask")
    assert deps is not None

    first = extract_uv_lock_hashes(project_dir, deps)
    second = extract_uv_lock_hashes(project_dir, deps)
    assert first == second


def test_missing_dependency_omitted_not_error() -> None:
    project_dir = REAL_WORLD_LOCKS / "flask-3.1.3"
    hashes = extract_uv_lock_hashes(project_dir, ["nonexistent-package==1.0"])
    assert hashes == {}


def test_no_genuine_version_marker_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "uv.lock").write_text(
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n',
            encoding="utf-8",
        )  # missing top-level int `version` marker
        assert extract_uv_lock_hashes(tmp_path, []) is None


def test_package_key_wrong_type_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, 'package = "not-a-list"\n')
        assert extract_uv_lock_hashes(tmp_path, []) is None


def test_locked_dependency_not_a_single_exact_pin_skipped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'wheels = [{ url = "requests-2.31.0.whl", hash = "sha256:'
            + "a" * 64
            + '" }]\n',
        )
        hashes = extract_uv_lock_hashes(tmp_path, ["requests>=2.0"])
        assert hashes == {}


def test_artifact_hash_candidates_skips_non_sha256_hash() -> None:
    assert not _artifact_hash_candidates(
        {"sdist": {"url": "pkg.tar.gz", "hash": "md5:deadbeef"}, "wheels": []}
    )
    assert _artifact_hash_candidates(
        {
            "sdist": None,
            "wheels": [{"url": "pkg.whl", "hash": "sha256:" + "b" * 64}],
        }
    ) == [("pkg.whl", "b" * 64)]
