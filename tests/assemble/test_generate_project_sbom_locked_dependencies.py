# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ``locked_dependencies`` opt-out on
:func:`pitloom.assemble.generate_project_sbom`: CLI/library flag,
``[tool.pitloom] locked-dependencies`` config, and their precedence.

See also: :mod:`tests.extract.test_project` for the lower-level
``read_project(include_locked_dependencies=...)`` coverage this builds on.
"""

from __future__ import annotations

import json
from pathlib import Path

from pitloom.assemble import generate_project_sbom
from pitloom.core.project import ProjectMetadata
from pitloom.extract.project import read_project

_PYPROJECT = """
[project]
name = "test-package"
version = "1.0.0"
dependencies = ["requests>=2.0"]
""".strip()

# "idna" is transitive-only: not a direct dependency, only reachable via the
# lock file's resolved package set -- the clearest signal for whether the
# cascade ran at all.
_PYLOCK = """
lock-version = "1.0"
created-by = "test"
[[packages]]
name = "requests"
version = "2.31.0"
[[packages]]
name = "idna"
version = "3.7"
""".strip()


def _write_project(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (tmp_path / "pylock.toml").write_text(_PYLOCK, encoding="utf-8")


def _package_names(sbom_json: str) -> set[str]:
    graph = json.loads(sbom_json)["@graph"]
    return {elem["name"] for elem in graph if elem["type"] == "software_Package"}


def test_generate_project_sbom_locked_dependencies_false_skips_cascade(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)

    sbom_json = generate_project_sbom(tmp_path, offline=True, locked_dependencies=False)

    assert "idna" not in _package_names(sbom_json)


def test_generate_project_sbom_locked_dependencies_true_runs_cascade(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)

    sbom_json = generate_project_sbom(tmp_path, offline=True, locked_dependencies=True)

    assert "idna" in _package_names(sbom_json)


def test_generate_project_sbom_locked_dependencies_config_only(
    tmp_path: Path,
) -> None:
    """No CLI/library override -- ``[tool.pitloom] locked-dependencies =
    false`` alone must skip the cascade."""
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT + "\n\n[tool.pitloom]\nlocked-dependencies = false\n",
        encoding="utf-8",
    )
    (tmp_path / "pylock.toml").write_text(_PYLOCK, encoding="utf-8")

    sbom_json = generate_project_sbom(tmp_path, offline=True)

    assert "idna" not in _package_names(sbom_json)


def test_generate_project_sbom_locked_dependencies_cli_overrides_config(
    tmp_path: Path,
) -> None:
    """An explicit ``locked_dependencies=True`` must win over a
    ``[tool.pitloom] locked-dependencies = false`` config default."""
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT + "\n\n[tool.pitloom]\nlocked-dependencies = false\n",
        encoding="utf-8",
    )
    (tmp_path / "pylock.toml").write_text(_PYLOCK, encoding="utf-8")

    sbom_json = generate_project_sbom(tmp_path, offline=True, locked_dependencies=True)

    assert "idna" in _package_names(sbom_json)


def test_generate_project_sbom_locked_dependencies_noop_when_metadata_presupplied(
    tmp_path: Path,
) -> None:
    """When ``project_metadata``/``pitloom_config`` are pre-supplied (as
    ``loom project`` does), ``locked_dependencies`` has no further effect --
    the cascade decision was already made when that metadata was read."""
    _write_project(tmp_path)
    project_metadata, pitloom_config, _ = read_project(
        tmp_path, include_locked_dependencies=True
    )
    assert isinstance(project_metadata, ProjectMetadata)

    sbom_json = generate_project_sbom(
        tmp_path,
        offline=True,
        project_metadata=project_metadata,
        pitloom_config=pitloom_config,
        locked_dependencies=False,
    )

    # Metadata already carries the resolved (cascade-on) dependencies --
    # passing locked_dependencies=False here changes nothing.
    assert "idna" in _package_names(sbom_json)
