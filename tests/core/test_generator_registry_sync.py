# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Loom ID registry auto-sync feature: ``generate_project_sbom``
/ ``generate_wheel_sbom`` / ``generate_env_sbom`` harvesting newly-minted ids
back into the resolved registry after generation, so a multi-step
project -> wheel -> env pipeline keeps stable ids without a manual
``pitloom ids generate``/``import`` step in between.

See also: :mod:`tests.core.test_ids_core` for ``IdRegistry.harvest()`` itself.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.assemble import (
    generate_env_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.ids import IdRegistry

from .conftest import _find_file_element, _make_wheel, _write_smoke_project


def test_generate_project_sbom_auto_updates_registry(tmp_path: Path) -> None:
    """A fresh, empty registry gets populated after generation -- no
    separate ``pitloom ids generate``/``import`` step needed."""
    _write_smoke_project(tmp_path)
    registry_path = tmp_path / "loom-ids.json"
    IdRegistry.new("smoke-project", path=registry_path).save()

    generate_project_sbom(tmp_path, registry=registry_path)

    reloaded = IdRegistry.load(registry_path)
    assert reloaded.files


def test_generate_project_sbom_respects_no_update_registry(tmp_path: Path) -> None:
    """``update_registry=False`` leaves an already-resolved registry untouched."""
    _write_smoke_project(tmp_path)
    registry_path = tmp_path / "loom-ids.json"
    IdRegistry.new("smoke-project", path=registry_path).save()

    generate_project_sbom(tmp_path, registry=registry_path, update_registry=False)

    reloaded = IdRegistry.load(registry_path)
    assert not reloaded.files
    assert not reloaded.entities


def test_generate_project_sbom_stable_ids_across_two_runs(tmp_path: Path) -> None:
    """A file's spdxId survives a *second* run even when the project's
    dependency list changes between runs -- which changes the run's own
    deterministic doc_uuid namespace, so this only holds because the
    registry intercepts the lookup with the id harvested from run 1."""
    pyproject_path = tmp_path / "pyproject.toml"
    _write_smoke_project(tmp_path)
    registry_path = tmp_path / "loom-ids.json"
    IdRegistry.new("smoke-project", path=registry_path).save()

    first_graph = json.loads(generate_project_sbom(tmp_path, registry=registry_path))[
        "@graph"
    ]
    first_id = _find_file_element(first_graph, "smoke_project/__init__.py")["spdxId"]

    pyproject_path.write_text(
        pyproject_path.read_text() + '\ndependencies = ["requests"]\n'
    )
    second_graph = json.loads(generate_project_sbom(tmp_path, registry=registry_path))[
        "@graph"
    ]
    second_id = _find_file_element(second_graph, "smoke_project/__init__.py")["spdxId"]

    assert first_id == second_id


def test_generate_project_sbom_does_not_auto_harvest_ai_packages(
    tmp_path: Path,
) -> None:
    """``ai_AIPackage`` elements are produced (however AI extras resolve),
    but are deliberately excluded from auto-harvest -- their correct
    registry key (the file's stem) only comes from ``pitloom ids
    generate``, not from the element's own (extraction-dependent) name."""
    _write_smoke_project(tmp_path)
    registry_path = tmp_path / "loom-ids.json"
    IdRegistry.new("smoke-project", path=registry_path).save()

    graph = json.loads(generate_project_sbom(tmp_path, registry=registry_path))[
        "@graph"
    ]
    assert any(e.get("type") == "ai_AIPackage" for e in graph)

    reloaded = IdRegistry.load(registry_path)
    assert not any(entry.type == "ai_AIPackage" for entry in reloaded.entities.values())


def test_generate_wheel_sbom_auto_updates_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    wheel_path = _make_wheel(tmp_path, "wheel-sync-pkg", "1.0.0")
    registry_path = tmp_path / "loom-ids.json"
    IdRegistry.new("wheel-sync-pkg", path=registry_path).save()

    generate_wheel_sbom(wheel_path, registry=registry_path)

    reloaded = IdRegistry.load(registry_path)
    assert reloaded.files


def test_generate_wheel_sbom_respects_no_update_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    wheel_path = _make_wheel(tmp_path, "wheel-sync-pkg", "1.0.0")
    registry_path = tmp_path / "loom-ids.json"
    IdRegistry.new("wheel-sync-pkg", path=registry_path).save()

    generate_wheel_sbom(wheel_path, registry=registry_path, update_registry=False)

    reloaded = IdRegistry.load(registry_path)
    assert not reloaded.files


def test_generate_env_sbom_auto_updates_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    registry_path = tmp_path / "loom-ids.json"
    IdRegistry.new("env-sync", path=registry_path).save()
    tree = [
        {
            "package": {
                "key": "requests",
                "package_name": "requests",
                "installed_version": "2.31.0",
            }
        }
    ]
    fake_result = subprocess.CompletedProcess(
        args=["pipdeptree", "--json-tree", "--all"],
        returncode=0,
        stdout=json.dumps(tree),
        stderr="",
    )

    with patch("subprocess.run", return_value=fake_result):
        generate_env_sbom(registry=registry_path)

    reloaded = IdRegistry.load(registry_path)
    assert reloaded.entities.get("requests") is not None
    assert reloaded.entities["requests"].type == "software_Package"


def test_generate_env_sbom_respects_no_update_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    registry_path = tmp_path / "loom-ids.json"
    IdRegistry.new("env-sync", path=registry_path).save()
    tree = [
        {
            "package": {
                "key": "requests",
                "package_name": "requests",
                "installed_version": "2.31.0",
            }
        }
    ]
    fake_result = subprocess.CompletedProcess(
        args=["pipdeptree", "--json-tree", "--all"],
        returncode=0,
        stdout=json.dumps(tree),
        stderr="",
    )

    with patch("subprocess.run", return_value=fake_result):
        generate_env_sbom(registry=registry_path, update_registry=False)

    reloaded = IdRegistry.load(registry_path)
    assert not reloaded.entities
