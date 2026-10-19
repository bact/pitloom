# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``poetry.lock`` (:mod:`pitloom.extract.lock.poetry`) read from a fixture
project and from real-world Poetry projects, alone and through
``read_pyproject()``.

See also: test_poetry.py (the extractor's own cases).
"""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract.lock.poetry import extract_poetry_lock_dependencies
from pitloom.extract.project.pyproject import read_pyproject
from tests.extract.lock.poetry_lock_shared import write_lock

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "projects"
POETRY_FIXTURE = FIXTURES / "sampleproject-poetry"
REAL_WORLD_LOCKS = (
    Path(__file__).parent.parent.parent / "fixtures" / "real-world-locks" / "poetry"
)


def test_fixture_lock_excludes_dev_group_dependency() -> None:
    """Real-world fixture: `pytest`/`mypy`/`ruff` live only in
    `[tool.poetry.group.dev.dependencies]` and must not appear."""
    result = extract_poetry_lock_dependencies(POETRY_FIXTURE)

    assert result is not None
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


def test_read_pyproject_populates_locked_dependency_hashes() -> None:
    """`_try_read_poetry()` applies `poetry.lock`-resolved dependencies directly,
    bypassing `cascade.py`, so hash extraction runs on this common poetry
    path too. See lock-hash-preservation.md."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "pkg"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        sha256 = "a" * 64
        write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n'
            f'files = [{{file = "requests-2.31.0-py3-none-any.whl", '
            f'hash = "sha256:{sha256}"}}]\n',
        )

        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")

        assert metadata.locked_dependency_hashes == {"requests": sha256}


def test_read_pyproject_pep621_project_with_minimal_poetry_still_reads_lock(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A PEP 621 ``[project]``-primary layout whose ``[tool.poetry]`` section
    holds only non-metadata settings (no ``name``) does not raise in
    ``extract_poetry_metadata()``; ``poetry.lock`` is still read."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\nversion = "1.0.0"\n'
            '[tool.poetry]\npackages = [{include = "pkg"}]\n',
            encoding="utf-8",
        )
        write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n',
        )

        with caplog.at_level(logging.WARNING):
            metadata, _config = read_pyproject(tmp_path / "pyproject.toml")

        assert metadata.name == "pkg"
        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: poetry.lock | Method: resolved_lockfile"
        )
        assert "could not be parsed" not in caplog.text  # [project] names it


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


def test_real_world_pendulum_hybrid_project_and_tool_poetry_tables() -> None:
    """`pendulum` declares both `[project]` (PEP 621) and `[tool.poetry]`
    -- confirms the hybrid shape resolves name/version via `[project]`
    while `poetry.lock` reading still runs."""
    metadata, _config = read_pyproject(
        REAL_WORLD_LOCKS / "pendulum-3.2.0" / "pyproject.toml"
    )

    assert metadata.name == "pendulum"
    assert metadata.locked_dependencies
    assert metadata.provenance["locked_dependencies"] == (
        "Source: poetry.lock | Method: resolved_lockfile"
    )


def test_real_world_cleo_tool_poetry_only() -> None:
    """`cleo` has `[tool.poetry]` only, no `[project]` table at all."""
    metadata, _config = read_pyproject(
        REAL_WORLD_LOCKS / "cleo-2.1.0" / "pyproject.toml"
    )

    assert metadata.name == "cleo"
    assert metadata.locked_dependencies
    assert metadata.provenance["locked_dependencies"] == (
        "Source: poetry.lock | Method: resolved_lockfile"
    )


def test_real_world_pastel_tool_poetry_only() -> None:
    """`pastel` uses legacy Poetry 1.x `category = "dev"` for all entries;
    verifies dev dependencies are excluded and locked_dependencies is empty."""
    metadata, _config = read_pyproject(
        REAL_WORLD_LOCKS / "pastel-0.2.1" / "pyproject.toml"
    )

    assert metadata.name == "pastel"
    assert metadata.locked_dependencies == []
    assert metadata.provenance["locked_dependencies"] == (
        "Source: poetry.lock | Method: resolved_lockfile"
    )


def test_real_world_tomlkit_has_no_main_group_dependencies() -> None:
    """`tomlkit` is a standalone TOML library with no runtime
    dependencies -- every entry in its `poetry.lock` belongs to the
    `dev`/docs/test groups, none to `main`. A real, valid "empty resolved
    set" case: `read_pyproject()` still succeeds, leaves
    `locked_dependencies` empty, but *does* record provenance for it --
    a real, parsed ``poetry.lock`` that authoritatively resolves to zero
    ``main``-group packages is a genuine answer, not the same as no lock
    file being present at all (see ``cascade.py``'s
    None-vs-``[]`` extractor contract)."""
    metadata, _config = read_pyproject(
        REAL_WORLD_LOCKS / "tomlkit-0.15.1" / "pyproject.toml"
    )

    assert metadata.name == "tomlkit"
    assert metadata.locked_dependencies == []
    assert metadata.provenance["locked_dependencies"] == (
        "Source: poetry.lock | Method: resolved_lockfile"
    )
