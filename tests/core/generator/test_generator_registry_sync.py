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
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._ids_types import FileEntry
from pitloom.assemble import (
    generate_env_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.assemble._generators_shared import _sync_registry
from pitloom.core.creation import CreationMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.ids import IdRegistry

from ...conftest import _assert_no_duplicate_spdx_ids
from ..conftest import _find_file_element, _make_wheel, _write_smoke_project


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

    assert not registry.has_entity_named("flores-200")


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


def test_sync_registry_logs_updated_when_net_counts_are_zero(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A harvest that releases one stale file key and adds a new one in
    the same pass nets to zero size change, but real content changed --
    the INFO message must say so (not "added 0 new file(s), 0 new
    entit(y/ies)", which reads as if nothing happened when a save did)."""
    registry_path = tmp_path / "loom-ids.json"
    shared_id = "https://spdx.org/spdxdocs/x-1#File-1"
    registry = IdRegistry.new("net-zero-change", path=registry_path)
    registry.files["old.py"] = FileEntry(spdx_id=shared_id, sha256="a" * 64)
    registry.save()

    ci = spdx3.CreationInfo(
        specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    file_obj = spdx3.software_File(
        spdxId=shared_id,
        name="new.py",
        creationInfo=ci,
        verifiedUsing=[
            spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue="b" * 64)
        ],
    )
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(ci)
    exporter.add_file(file_obj)

    with caplog.at_level("INFO"):
        _sync_registry(exporter, registry, True)

    assert "old.py" not in registry.files
    assert registry.files["new.py"].spdx_id == shared_id
    assert "updated stale entries" in caplog.text
    assert "added 0 new file(s)" not in caplog.text


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
    assert not any(type_name == "ai_AIPackage" for type_name, _ in reloaded.entities)


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
    assert ("software_Package", "requests") in reloaded.entities


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


def _make_nested_wheel(tmp_path: Path, name: str, version: str) -> Path:
    """A minimal wheel whose package directory holds both a file and a
    nested subdirectory -- reproduces the id mint-collision bug: on a
    second run (registry auto-harvested from the first, same doc_uuid
    since ``generate_wheel_sbom`` never folds file content into it), a
    file's registry hit doesn't advance the ``File`` counter, so an
    unlooked-up directory minted right after would land on the exact
    number the registry already gave that file, without reservation."""
    wheel_path = tmp_path / f"{name}-{version}-py3-none-any.whl"
    metadata_body = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr(f"{name}-{version}.dist-info/METADATA", metadata_body)
        zf.writestr(f"{name}/a.py", "# a\n")
        zf.writestr(f"{name}/sub/b.py", "# b\n")
    return wheel_path


def test_generate_wheel_sbom_repeated_runs_never_duplicate_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three consecutive runs on the *same* wheel, with the registry
    auto-harvested between each, must never mint a duplicate spdxId, and
    -- since nothing about the wheel or its registry-visible content
    changes -- must produce byte-identical output every time.

    Non-vacuous: the registry is confirmed non-empty before runs 2/3, and
    run 2 is confirmed to actually reuse at least one file id and one
    directory id from the registry (both the directory-lookup fix and the
    file-lookup path it already had)."""
    monkeypatch.chdir(tmp_path)
    wheel_path = _make_nested_wheel(tmp_path, "collisiondemo", "1.0.0")
    registry_path = tmp_path / "loom-ids.json"
    IdRegistry.new("collisiondemo", path=registry_path).save()
    creation_metadata = CreationMetadata(creation_datetime="2026-01-01T00:00:00+00:00")

    def _run() -> str:
        return generate_wheel_sbom(
            wheel_path, registry=registry_path, creation_metadata=creation_metadata
        )

    first_json = _run()
    _assert_no_duplicate_spdx_ids(first_json)

    registry_after_first = IdRegistry.load(registry_path)
    assert registry_after_first.files
    assert registry_after_first.entities

    real_lookup_file = IdRegistry.lookup_file
    real_lookup_entity = IdRegistry.lookup_entity
    file_hits = 0
    entity_hits = 0

    def _counting_lookup_file(self: IdRegistry, path: str, sha256: str) -> str | None:
        nonlocal file_hits
        result = real_lookup_file(self, path, sha256)
        if result is not None:
            file_hits += 1
        return result

    def _counting_lookup_entity(
        self: IdRegistry, name: str, type_name: str
    ) -> str | None:
        nonlocal entity_hits
        result = real_lookup_entity(self, name, type_name)
        if result is not None:
            entity_hits += 1
        return result

    with (
        patch.object(IdRegistry, "lookup_file", _counting_lookup_file),
        patch.object(IdRegistry, "lookup_entity", _counting_lookup_entity),
    ):
        second_json = _run()
    _assert_no_duplicate_spdx_ids(second_json)

    assert file_hits >= 1
    assert entity_hits >= 1

    third_json = _run()
    _assert_no_duplicate_spdx_ids(third_json)

    assert first_json == second_json == third_json


def test_generate_wheel_sbom_new_file_does_not_collide_with_registered_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file added to the wheel *after* the registry was populated has
    nothing to look up -- only the id-reservation fix (not the directory
    lookup alone) stops its fresh mint from landing on a number the
    registry already gave a sibling element in this exact document
    namespace (``generate_wheel_sbom`` never folds wheel content into
    ``doc_uuid``, so both runs share one namespace, same as a real rebuild
    between two ``loom wheel`` invocations)."""
    monkeypatch.chdir(tmp_path)
    wheel_path = _make_nested_wheel(tmp_path, "growingdemo", "1.0.0")
    registry_path = tmp_path / "loom-ids.json"
    IdRegistry.new("growingdemo", path=registry_path).save()
    creation_metadata = CreationMetadata(creation_datetime="2026-01-01T00:00:00+00:00")

    first_json = generate_wheel_sbom(
        wheel_path, registry=registry_path, creation_metadata=creation_metadata
    )
    _assert_no_duplicate_spdx_ids(first_json)
    assert IdRegistry.load(registry_path).files

    # Rebuild the "same" wheel with one extra, never-before-seen file --
    # name/version/dependencies are unchanged, so doc_uuid (and therefore
    # the document namespace the registry's ids were harvested under)
    # stays identical, exactly like a real rebuild between two runs.
    with zipfile.ZipFile(wheel_path, "a") as zf:
        zf.writestr("growingdemo/c.py", "# c\n")

    second_json = generate_wheel_sbom(
        wheel_path, registry=registry_path, creation_metadata=creation_metadata
    )
    _assert_no_duplicate_spdx_ids(second_json)
