# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``poetry.lock`` SHA-256 digest extraction
(:mod:`pitloom.extract._poetry_lock_hashes`).

Poetry's hash location isn't uniform across lock versions -- both real
fixture shapes are exercised: ``pendulum-3.2.0`` (lock-version 2.1,
per-package ``files``) and ``pastel-0.2.1`` (lock-version 1.1, legacy
top-level ``[metadata.files]``).
"""

import tempfile
from pathlib import Path

from packaging.utils import canonicalize_name

from pitloom.extract._poetry_lock import extract_poetry_lock_dependencies
from pitloom.extract._poetry_lock_hashes import (
    _filename_matches_version,
    extract_poetry_lock_hashes,
)

REAL_WORLD_LOCKS = (
    Path(__file__).parent.parent / "fixtures" / "real-world-locks" / "poetry"
)

_METADATA = '[metadata]\nlock-version = "2.1"\n'


def _write_lock(tmp_dir: Path, body: str) -> None:
    (tmp_dir / "poetry.lock").write_text(body + _METADATA, encoding="utf-8")


#: six's wheel hash from
#: tests/fixtures/real-world-locks/poetry/pendulum-3.2.0/poetry.lock
#: (modern per-package `files`) -- its sdist hash differs, confirming
#: wheel-over-sdist preference.
_SIX_WHEEL_HASH = "8abb2f1d86890a2dfb989f9a77cfcfd3e47c2a354b01111771326f8aa26e0254"

#: appdirs' wheel hash from
#: tests/fixtures/real-world-locks/poetry/pastel-0.2.1/poetry.lock
#: (legacy top-level `[metadata.files]`).
_APPDIRS_WHEEL_HASH = "a841dacd6b99318a741b166adb07e19ee71a274450e68237b4650ca1055ab128"


def test_no_lock_file_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert extract_poetry_lock_hashes(Path(tmp), []) is None


def test_real_world_pendulum_six_wheel_hash_per_package_files() -> None:
    project_dir = REAL_WORLD_LOCKS / "pendulum-3.2.0"
    deps = extract_poetry_lock_dependencies(project_dir)
    assert deps is not None

    hashes = extract_poetry_lock_hashes(project_dir, deps)
    assert hashes is not None
    assert hashes[canonicalize_name("six")] == _SIX_WHEEL_HASH


def test_real_world_pastel_appdirs_wheel_hash_legacy_metadata_files() -> None:
    project_dir = REAL_WORLD_LOCKS / "pastel-0.2.1"

    # appdirs is a "dev"-category-only entry in this fixture, so it never
    # survives extract_poetry_lock_dependencies()'s main-group filter --
    # this test targets hash extraction's independent name/version lookup
    # against the legacy `[metadata.files]` table directly.
    hashes = extract_poetry_lock_hashes(project_dir, ["appdirs==1.4.4"])
    assert hashes is not None
    assert hashes[canonicalize_name("appdirs")] == _APPDIRS_WHEEL_HASH


def test_real_world_pastel_colorama_wheel_hash_matches_resolved_version() -> None:
    """Regression: when `[metadata.files]` contains files for multiple
    versions of the same package (e.g. across marker branches), hash
    extraction must only pick files matching the resolved version, not
    arbitrarily pick an older version's wheel."""
    project_dir = REAL_WORLD_LOCKS / "pastel-0.2.1"
    colorama_043_hash = (
        "7d73d2a99753107a36ac6b455ee49046802e59d9d076ef8e47b61499fa29afff"
    )
    colorama_041_hash = (
        "f8ac84de7840f5b9c4e3347b3c1eaa50f7e49c2b07596221daec5edaabbd7c48"
    )

    hashes_043 = extract_poetry_lock_hashes(project_dir, ["colorama==0.4.3"])
    assert hashes_043 is not None
    assert hashes_043[canonicalize_name("colorama")] == colorama_043_hash

    hashes_041 = extract_poetry_lock_hashes(project_dir, ["colorama==0.4.1"])
    assert hashes_041 is not None
    assert hashes_041[canonicalize_name("colorama")] == colorama_041_hash


def test_determinism_same_lock_same_hash() -> None:
    project_dir = REAL_WORLD_LOCKS / "pendulum-3.2.0"
    deps = extract_poetry_lock_dependencies(project_dir)
    assert deps is not None

    first = extract_poetry_lock_hashes(project_dir, deps)
    second = extract_poetry_lock_hashes(project_dir, deps)
    assert first == second


def test_missing_dependency_omitted_not_error() -> None:
    project_dir = REAL_WORLD_LOCKS / "pendulum-3.2.0"
    hashes = extract_poetry_lock_hashes(project_dir, ["nonexistent-package==1.0"])
    assert hashes == {}


def test_package_key_wrong_type_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, 'package = "not-a-list"\n')
        assert extract_poetry_lock_hashes(tmp_path, []) is None


def test_locked_dependency_not_a_single_exact_pin_skipped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'files = [{file = "requests-2.31.0.whl", hash = "sha256:'
            + "a" * 64
            + '"}]\n',
        )
        hashes = extract_poetry_lock_hashes(tmp_path, ["requests>=2.0"])
        assert hashes == {}


def test_filename_matches_version_rejects_non_string_filename() -> None:
    assert not _filename_matches_version(None, "1.0.0")


def test_filename_matches_version_arbitrary_equality_falls_back_to_substring() -> None:
    """A ``===``-pinned, non-PEP-440 *expected_version* can't be built into
    a `Version` to compare against a parsed wheel/sdist version -- falls
    back to the plain substring/suffix heuristic."""
    assert _filename_matches_version(
        "pkg-2021.01.01-legacy-py3-none-any.whl", "2021.01.01-legacy"
    )
    assert not _filename_matches_version(
        "pkg-2021.01.02-legacy-py3-none-any.whl", "2021.01.01-legacy"
    )


def test_filename_matches_version_unparseable_filename_falls_back_to_substring() -> (
    None
):
    """A filename that's neither a valid wheel nor sdist filename (an
    unrecognized extension) still falls back to the substring/suffix
    heuristic rather than raising."""
    assert _filename_matches_version("pkg-1.0.0-linux.tar.bz2", "1.0.0")
    assert not _filename_matches_version("pkg-2.0.0-linux.tar.bz2", "1.0.0")
