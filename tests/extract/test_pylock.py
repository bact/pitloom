# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for PEP 751 ``pylock.toml`` dependency parsing
(:mod:`pitloom.extract._pylock`) and its overlay onto
``ProjectMetadata.locked_dependencies`` via ``read_pyproject()``.

See also: test_poetry_lock.py for the sibling ``poetry.lock`` extractor
this module's tests mirror in shape.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract._pylock import _pinned_dep_for_package, extract_pylock_dependencies
from pitloom.extract._pyproject import read_pyproject

_LOCK_VERSION = 'lock-version = "1.0"\ncreated-by = "test"\n'


def _write_lock(tmp_dir: Path, packages: str = "") -> None:
    (tmp_dir / "pylock.toml").write_text(_LOCK_VERSION + packages, encoding="utf-8")


def test_no_lock_file_returns_empty_list() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert not extract_pylock_dependencies(Path(tmp))


def test_malformed_toml_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pylock.toml").write_text(
            "this is not [ valid toml", encoding="utf-8"
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert not result
        assert "Failed to parse" in caplog.text


def test_missing_lock_version_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pylock.toml").write_text(
            '[[packages]]\nname = "requests"\nversion = "2.31.0"\n',
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert not result
        assert "lock-version" in caplog.text


def test_package_included() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, '[[packages]]\nname = "requests"\nversion = "2.31.0"\n')

        assert extract_pylock_dependencies(tmp_path) == ["requests==2.31.0"]


def test_packages_key_not_a_list_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, 'packages = "not-a-list"\n')

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert not result
        assert "expected a list" in caplog.text


def test_pinned_dep_for_package_non_dict_entry_returns_none() -> None:
    assert _pinned_dep_for_package("not-a-dict") is None
    assert _pinned_dep_for_package(["still", "not", "a", "dict"]) is None


def test_malformed_package_entry_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[packages]]\nversion = "1.0.0"\n\n'
            '[[packages]]\nname = "complete-pkg"\nversion = "2.0.0"\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert result == ["complete-pkg==2.0.0"]
        assert "malformed" in caplog.text.lower()


def test_missing_version_skipped_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, '[[packages]]\nname = "no-version"\n')

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert not result
        assert "missing" in caplog.text.lower()


@pytest.mark.parametrize("source_key", ["vcs", "directory", "archive"])
def test_non_registry_sourced_package_excluded(
    source_key: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A package pinned via `vcs`/`directory`/`archive` has no meaningful
    PyPI version pin -- excluded the same way poetry.lock's equivalent
    non-registry sources are excluded."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[packages]]\nname = "local-dep"\nversion = "0.1.0"\n'
            f'[packages.{source_key}]\nurl = "https://example.com"\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert not result
        assert "local-dep" in caplog.text


def test_sdist_sourced_package_included() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[packages]]\nname = "requests"\nversion = "2.31.0"\n'
            '[packages.sdist]\nurl = "https://example.com/requests-2.31.0.tar.gz"\n',
        )

        assert extract_pylock_dependencies(tmp_path) == ["requests==2.31.0"]


def test_read_pyproject_populates_locked_dependencies() -> None:
    """Integration: `read_pyproject()` overlays `pylock.toml` parsing onto
    `ProjectMetadata.locked_dependencies` with its own provenance entry,
    for a plain PEP 621 project (no `[tool.poetry]` involved)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        _write_lock(tmp_path, '[[packages]]\nname = "requests"\nversion = "2.31.0"\n')

        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")

        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: pylock.toml | Method: resolved_lockfile"
        )


def test_read_pyproject_no_lock_file_leaves_locked_dependencies_empty() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\nversion = "1.0.0"\n', encoding="utf-8"
        )

        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")

        assert metadata.locked_dependencies == []
        assert "locked_dependencies" not in metadata.provenance


def test_read_pyproject_pylock_takes_priority_over_poetry_lock(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: when both a `poetry.lock` and a `pylock.toml` are
    present, PEP 751's `pylock.toml` wins -- and the override is never
    silent."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "pkg"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        (tmp_path / "poetry.lock").write_text(
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n',
            encoding="utf-8",
        )
        _write_lock(tmp_path, '[[packages]]\nname = "httpx"\nversion = "0.27.0"\n')

        with caplog.at_level(logging.WARNING):
            metadata, _config = read_pyproject(tmp_path / "pyproject.toml")

        assert metadata.locked_dependencies == ["httpx==0.27.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: pylock.toml | Method: resolved_lockfile"
        )
        assert "pylock.toml (PEP 751) takes priority" in caplog.text
