# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ``use_lockfile`` opt-out on
:func:`pitloom.assemble.generate_project_sbom`: CLI/library flag,
``[tool.pitloom] use-lockfile`` config, and their precedence.

See also: :mod:`tests.extract.test_project` for the lower-level
``read_project(include_locked_dependencies=...)`` coverage this builds on.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.core.project import ProjectMetadata
from pitloom.extract.project import read_project
from tests.fixtures.locked_deps import write_locked_deps_project


def _write_project(tmp_path: Path) -> None:
    write_locked_deps_project(tmp_path)


def _package_names(sbom_json: str) -> set[str]:
    graph = json.loads(sbom_json)["@graph"]
    return {elem["name"] for elem in graph if elem["type"] == "software_Package"}


def test_generate_project_sbom_use_lockfile_false_skips_cascade(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)

    sbom_json = generate_project_sbom(tmp_path, offline=True, use_lockfile=False)

    assert "idna" not in _package_names(sbom_json)


def test_generate_project_sbom_use_lockfile_true_runs_cascade(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)

    sbom_json = generate_project_sbom(tmp_path, offline=True, use_lockfile=True)

    assert "idna" in _package_names(sbom_json)


def test_generate_project_sbom_use_lockfile_config_only(
    tmp_path: Path,
) -> None:
    """No CLI/library override -- ``[tool.pitloom] use-lockfile = false``
    alone must skip the cascade."""
    write_locked_deps_project(tmp_path, disable_cascade_in_config=True)

    sbom_json = generate_project_sbom(tmp_path, offline=True)

    assert "idna" not in _package_names(sbom_json)


def test_generate_project_sbom_use_lockfile_cli_overrides_config(
    tmp_path: Path,
) -> None:
    """An explicit ``use_lockfile=True`` must win over a
    ``[tool.pitloom] use-lockfile = false`` config default."""
    write_locked_deps_project(tmp_path, disable_cascade_in_config=True)

    sbom_json = generate_project_sbom(tmp_path, offline=True, use_lockfile=True)

    assert "idna" in _package_names(sbom_json)


def test_generate_project_sbom_use_lockfile_noop_when_metadata_presupplied(
    tmp_path: Path,
) -> None:
    """When ``project_metadata``/``pitloom_config`` are pre-supplied (as
    ``loom project`` does), ``use_lockfile`` has no further effect -- the
    cascade decision was already made when that metadata was read."""
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
        use_lockfile=False,
    )

    # Metadata already carries the resolved (cascade-on) dependencies --
    # passing use_lockfile=False here changes nothing.
    assert "idna" in _package_names(sbom_json)


def test_generate_project_sbom_partial_presupply_warns_and_discards(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: supplying only ONE of project_metadata/pitloom_config
    (not the documented both-or-neither contract) must not silently
    re-resolve and discard the caller's supplied value -- a WARNING: has
    to explain the deviation, per AGENTS.md's "no silent deviations" rule."""
    _write_project(tmp_path)
    caller_metadata = ProjectMetadata(name="caller-supplied-name")

    with caplog.at_level(logging.WARNING):
        sbom_json = generate_project_sbom(
            tmp_path,
            offline=True,
            project_metadata=caller_metadata,
        )

    # The caller-supplied metadata (name="caller-supplied-name") was
    # discarded and re-resolved from disk instead -- "locked-app" wins.
    assert "caller-supplied-name" not in sbom_json
    assert "locked-app" in sbom_json
    assert "must be supplied together" in caplog.text
    assert "project_metadata" in caplog.text
