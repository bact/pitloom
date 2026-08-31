# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``poetry.lock`` transitive-dependency parsing
(:mod:`pitloom.extract._poetry_lock`).

See also: test_poetry_parsing.py for low-level ``[tool.poetry]`` parsing,
test_poetry_pyproject.py for ``read_pyproject()`` integration; this file
covers the sibling ``poetry.lock`` extractor those don't.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract._poetry_lock import extract_poetry_lock_dependencies
from pitloom.extract._pyproject import read_pyproject

FIXTURES = Path(__file__).parent.parent / "fixtures" / "projects"
POETRY_FIXTURE = FIXTURES / "sampleproject-poetry"


def _write_lock(tmp_dir: Path, content: str) -> None:
    (tmp_dir / "poetry.lock").write_text(content, encoding="utf-8")


def test_no_lock_file_returns_empty_list() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert extract_poetry_lock_dependencies(Path(tmp)) == []


def test_malformed_toml_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, "this is not [ valid toml")

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert result == []
        assert "Failed to parse" in caplog.text


def test_main_group_package_included() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n',
        )

        result = extract_poetry_lock_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]


def test_dev_only_group_package_excluded() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "pytest"\nversion = "8.0.0"\ngroups = ["dev"]\n',
        )

        assert extract_poetry_lock_dependencies(tmp_path) == []


def test_package_in_main_and_dev_groups_included() -> None:
    """A package listed under both `main` and another group still counts
    -- only *exclusively* non-main packages are dropped."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "shared-pkg"\nversion = "1.0.0"\n'
            'groups = ["main", "dev"]\n',
        )

        assert extract_poetry_lock_dependencies(tmp_path) == ["shared-pkg==1.0.0"]


def test_missing_groups_key_defaults_to_main() -> None:
    """Older ``poetry.lock`` schema versions may lack a ``groups`` key
    entirely -- treat that as the default (``main``), not "exclude"."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, '[[package]]\nname = "legacy-pkg"\nversion = "1.0.0"\n')

        assert extract_poetry_lock_dependencies(tmp_path) == ["legacy-pkg==1.0.0"]


def test_malformed_package_entry_skipped() -> None:
    """A package table missing ``name``/``version`` is skipped, not a
    crash -- the rest of the lock file is still processed."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "incomplete"\n\n'
            '[[package]]\nname = "complete-pkg"\nversion = "2.0.0"\n',
        )

        assert extract_poetry_lock_dependencies(tmp_path) == ["complete-pkg==2.0.0"]


def test_fixture_lock_excludes_dev_group_dependency() -> None:
    """Real-world fixture: `pytest`/`mypy`/`ruff` live only in
    `[tool.poetry.group.dev.dependencies]` and must not appear."""
    result = extract_poetry_lock_dependencies(POETRY_FIXTURE)

    names = {dep.split("==", maxsplit=1)[0] for dep in result}
    assert "pytest" not in names
    assert "numpy" in names


def test_read_pyproject_populates_locked_dependencies() -> None:
    """Integration: `read_pyproject()` wires `poetry.lock` parsing into
    `ProjectMetadata.locked_dependencies` with its own provenance entry."""
    metadata, _config = read_pyproject(POETRY_FIXTURE / "pyproject.toml")

    assert metadata.locked_dependencies
    assert metadata.provenance["locked_dependencies"] == (
        "Source: poetry.lock | Method: resolved_lockfile"
    )


def test_read_pyproject_no_lock_file_leaves_locked_dependencies_empty() -> None:
    """A Poetry project with no `poetry.lock` at all gets an empty
    `locked_dependencies` and no provenance entry for it -- optional
    enrichment, never a requirement."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "pkg"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )

        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")

        assert metadata.locked_dependencies == []
        assert "locked_dependencies" not in metadata.provenance
