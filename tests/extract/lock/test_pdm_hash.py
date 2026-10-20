# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``pdm.lock`` SHA-256 digest extraction
(:mod:`pitloom.extract.lock.pdm_hash`).
"""

import tempfile
from pathlib import Path

from packaging.utils import canonicalize_name

from pitloom.extract.lock.pdm import extract_pdm_lock_dependencies
from pitloom.extract.lock.pdm_hash import extract_pdm_lock_hashes

REAL_WORLD_LOCKS = (
    Path(__file__).parent.parent.parent / "fixtures" / "real-world-locks" / "pdm"
)

_METADATA = '[metadata]\nlock_version = "4.5.1"\n'


def _write_lock(tmp_dir: Path, body: str) -> None:
    (tmp_dir / "pdm.lock").write_text(body + _METADATA, encoding="utf-8")


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


def test_missing_dependency_omitted_not_error() -> None:
    project_dir = REAL_WORLD_LOCKS / "pdm-2.29.0"
    hashes = extract_pdm_lock_hashes(project_dir, ["nonexistent-package==1.0"])
    assert hashes == {}


def test_package_key_wrong_type_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, 'package = "not-a-list"\n')
        assert extract_pdm_lock_hashes(tmp_path, []) is None


def test_locked_dependency_not_a_single_exact_pin_skipped() -> None:
    """A `locked_dependencies` entry that isn't a single exact pin (e.g.
    a future extractor that doesn't always emit one) is skipped, not an
    error."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'files = [{file = "requests-2.31.0.whl", hash = "sha256:'
            + "a" * 64
            + '"}]\n',
        )
        hashes = extract_pdm_lock_hashes(tmp_path, ["requests>=2.0"])
        assert hashes == {}


def test_pep440_version_equivalence_collects_all_branch_candidates() -> None:
    """Branches specifying PEP 440 equivalent versions (e.g. 1.0 and 1.0.0)
    group together so all candidates are considered (a wheel on 1.0.0 is
    preferred over an sdist on 1.0)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        wheel_hash = "b" * 64
        _write_lock(
            tmp_path,
            '[[package]]\nname = "foo"\nversion = "1.0"\n'
            'files = [{file = "foo-1.0.tar.gz", hash = "sha256:' + "a" * 64 + '"}]\n\n'
            '[[package]]\nname = "foo"\nversion = "1.0.0"\n'
            'files = [{file = "foo-1.0.0-py3-none-any.whl", hash = "sha256:'
            + wheel_hash
            + '"}]\n',
        )
        hashes = extract_pdm_lock_hashes(tmp_path, ["foo==1.0"])
        assert hashes == {"foo": wheel_hash}


def test_missing_lock_version_marker_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pdm.lock").write_text(
            '[[package]]\nname = "foo"\nversion = "1.0"\n', encoding="utf-8"
        )
        assert extract_pdm_lock_hashes(tmp_path, ["foo==1.0"]) is None
