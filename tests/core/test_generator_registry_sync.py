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
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import (
    generate_env_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.assemble._generators import _sync_registry
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.ids import IdRegistry

from .conftest import _find_file_element, _make_wheel, _write_smoke_project


def _exporter_with_one_package() -> Spdx3JsonExporter:
    ci = spdx3.CreationInfo(
        specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    pkg = spdx3.software_Package(
        spdxId="https://spdx.org/spdxdocs/x-1#Package-1",
        name="requests",
        creationInfo=ci,
    )
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(ci)
    exporter.add_package(pkg)
    return exporter


def test_sync_registry_excludes_dataset_packages(tmp_path: Path) -> None:
    """``dataset_DatasetPackage`` is excluded the same way ``ai_AIPackage``
    is: nothing in ``build()`` ever looks a dataset up by name, so a
    harvested entry would just be dead, silently-overwritten weight."""
    ci = spdx3.CreationInfo(
        specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    dataset = spdx3.dataset_DatasetPackage(
        spdxId="https://spdx.org/spdxdocs/x-1#DatasetPackage-1",
        name="flores-200",
        creationInfo=ci,
    )
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(ci)
    exporter.add_package(dataset)

    registry_path = tmp_path / "loom-ids.json"
    registry = IdRegistry.new("dataset-exclusion", path=registry_path)

    _sync_registry(exporter, registry, True)

    assert "flores-200" not in registry.entities


def test_sync_registry_skips_when_registry_has_no_path(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A registry resolved without an on-disk path (e.g. constructed
    programmatically) is skipped entirely, not harvested into or saved."""
    registry = IdRegistry.new("no-path")
    exporter = _exporter_with_one_package()

    with caplog.at_level("WARNING"):
        _sync_registry(exporter, registry, True)

    assert not registry.entities
    assert "no file path resolved" in caplog.text


def test_sync_registry_logs_warning_on_save_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A save failure is logged, not raised -- it must never break SBOM
    generation itself."""
    registry_path = tmp_path / "loom-ids.json"
    registry = IdRegistry.new("save-fails", path=registry_path)
    exporter = _exporter_with_one_package()

    with patch.object(registry, "save", side_effect=OSError("disk full")):
        with caplog.at_level("WARNING"):
            _sync_registry(exporter, registry, True)

    assert "failed to save" in caplog.text
    assert not registry_path.exists()


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
    first_deps = [e["name"] for e in first_graph if e.get("type") == "software_Package"]
    assert "requests" not in first_deps

    # Insert into [project] (right after "version = ..."), not appended
    # blindly at end of file -- appending after the file's last table
    # header ([tool.hatch.build.targets.wheel]) would silently nest the
    # new key under *that* table instead of [project], leaving
    # project_metadata.dependencies (and therefore doc_uuid) unchanged
    # and this test not actually exercising what its docstring claims.
    pyproject_path.write_text(
        pyproject_path.read_text().replace(
            'version = "0.1.0"\n',
            'version = "0.1.0"\ndependencies = ["requests"]\n',
        )
    )
    second_graph = json.loads(generate_project_sbom(tmp_path, registry=registry_path))[
        "@graph"
    ]
    second_id = _find_file_element(second_graph, "smoke_project/__init__.py")["spdxId"]
    second_deps = [
        e["name"] for e in second_graph if e.get("type") == "software_Package"
    ]

    # Confirm the dependency list -- and therefore doc_uuid -- actually
    # changed between runs, so a matching id below is meaningful and not
    # a byte-identical rerun that would pass even without the registry.
    assert "requests" in second_deps
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
