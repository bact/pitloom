# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the stable file/entity -> SPDX ID registry (pitloom.ids)."""

# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.__main__ import _build_parser, _run_ids_cli
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.ids import (
    DEFAULT_REGISTRY_FILENAME,
    EntityEntry,
    FileEntry,
    IdRegistry,
    resolve_registry,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_bytes(b"print(1)\n")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.txt").write_bytes(b"hello\n")
    return tmp_path


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


def test_generate_indexes_files_with_hashes(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry = IdRegistry.new("proj")
    registry.generate([Path("src"), Path("data")], root)

    assert set(registry.files) == {"src/a.py", "data/x.txt"}
    assert registry.files["src/a.py"].sha256 == _sha256(b"print(1)\n")
    assert registry.files["data/x.txt"].sha256 == _sha256(b"hello\n")
    # Every id lives in the registry namespace with a #File-<n> fragment.
    for entry in registry.files.values():
        assert entry.spdx_id.startswith(f"{registry.namespace}#File-")


def test_generate_is_stable_for_unchanged_files(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry = IdRegistry.new("proj")
    registry.generate([Path("src"), Path("data")], root)
    before = {p: e.spdx_id for p, e in registry.files.items()}

    registry.generate([Path("src"), Path("data")], root)
    after = {p: e.spdx_id for p, e in registry.files.items()}
    assert after == before


def test_generate_mints_new_id_for_changed_content(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry = IdRegistry.new("proj")
    registry.generate([Path("data")], root)
    old_id = registry.files["data/x.txt"].spdx_id

    (root / "data" / "x.txt").write_bytes(b"changed\n")
    registry.generate([Path("data")], root)

    new_entry = registry.files["data/x.txt"]
    assert new_entry.spdx_id != old_id
    assert new_entry.sha256 == _sha256(b"changed\n")


def test_generate_preserves_namespace_across_regeneration(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry_path = root / DEFAULT_REGISTRY_FILENAME
    registry = IdRegistry.new("proj", path=registry_path)
    registry.generate([Path("src")], root)
    registry.save()
    namespace = registry.namespace

    reloaded = IdRegistry.load(registry_path)
    (root / "data" / "new.txt").write_bytes(b"more\n")
    reloaded.generate([Path("src"), Path("data")], root)
    assert reloaded.namespace == namespace
    # Old entries kept, new files appended with fresh ids.
    assert reloaded.files["src/a.py"].spdx_id == registry.files["src/a.py"].spdx_id
    assert "data/new.txt" in reloaded.files


def test_generate_registers_ai_model_entity(tmp_path: Path) -> None:
    root = tmp_path
    models = root / "models"
    models.mkdir()
    # GGUF magic bytes make this file a detectable AI model.
    (models / "sentimentdemo.bin").write_bytes(b"GGUF" + b"\x00" * 16)

    registry = IdRegistry.new("proj")
    registry.generate([Path("models")], root)

    assert "models/sentimentdemo.bin" in registry.files
    assert "sentimentdemo" in registry.entities
    entity = registry.entities["sentimentdemo"]
    assert entity.type == "ai_AIPackage"
    assert entity.spdx_id.startswith(f"{registry.namespace}#AIPackage-")


def test_generate_skips_registry_file_itself(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry_path = root / DEFAULT_REGISTRY_FILENAME
    registry = IdRegistry.new("proj", path=registry_path)
    registry.generate([Path(".")], root)
    registry.save()

    reloaded = IdRegistry.load(registry_path)
    reloaded.generate([Path(".")], root)
    assert DEFAULT_REGISTRY_FILENAME not in reloaded.files


# ---------------------------------------------------------------------------
# lookup
# ---------------------------------------------------------------------------


def test_lookup_file_requires_path_and_hash_match(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry = IdRegistry.new("proj")
    registry.generate([Path("data")], root)

    good_hash = _sha256(b"hello\n")
    spdx_id = registry.lookup_file("data/x.txt", good_hash)
    assert spdx_id == registry.files["data/x.txt"].spdx_id

    # Hash mismatch -> None (stale entries are inert, never wrong).
    assert registry.lookup_file("data/x.txt", "0" * 64) is None
    # Unknown path -> None.
    assert registry.lookup_file("data/other.txt", good_hash) is None


def test_lookup_entity_requires_type_match() -> None:
    registry = IdRegistry(
        namespace="https://spdx.org/spdxdocs/x-1",
        entities={
            "model": EntityEntry(
                type="ai_AIPackage", spdx_id="https://spdx.org/spdxdocs/x-1#AIPackage-1"
            )
        },
    )
    assert registry.lookup_entity("model", "ai_AIPackage") == (
        "https://spdx.org/spdxdocs/x-1#AIPackage-1"
    )
    assert registry.lookup_entity("model", "software_Package") is None
    assert registry.lookup_entity("other", "ai_AIPackage") is None


# ---------------------------------------------------------------------------
# save / load round trip
# ---------------------------------------------------------------------------


def test_save_load_round_trip(tmp_path: Path) -> None:
    registry = IdRegistry(
        namespace="https://spdx.org/spdxdocs/x-1",
        files={
            "a.txt": FileEntry(
                spdx_id="https://spdx.org/spdxdocs/x-1#File-1", sha256="ab" * 32
            )
        },
        entities={
            "model": EntityEntry(
                type="ai_AIPackage", spdx_id="https://spdx.org/spdxdocs/x-1#AIPackage-1"
            )
        },
    )
    registry_path = tmp_path / "reg.json"
    registry.save(registry_path)

    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["namespace"] == registry.namespace

    reloaded = IdRegistry.load(registry_path)
    assert reloaded.namespace == registry.namespace
    assert reloaded.files == registry.files
    assert reloaded.entities == registry.entities


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        IdRegistry.load(tmp_path / "absent.json")


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        IdRegistry.load(bad)


def test_load_missing_namespace_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"version": 1, "files": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="namespace"):
        IdRegistry.load(bad)


# ---------------------------------------------------------------------------
# auto-discovery (find / resolve_registry)
# ---------------------------------------------------------------------------


def test_find_walks_up_from_start_directory(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry_path = root / DEFAULT_REGISTRY_FILENAME
    registry = IdRegistry.new("proj", path=registry_path)
    registry.save()

    found = IdRegistry.find(start=root / "src")
    assert found is not None
    assert found.namespace == registry.namespace


def test_find_from_cwd(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry = IdRegistry.new("proj", path=root / DEFAULT_REGISTRY_FILENAME)
    registry.save()

    old_cwd = Path.cwd()
    os.chdir(root / "data")
    try:
        found = IdRegistry.find()
    finally:
        os.chdir(old_cwd)
    assert found is not None
    assert found.namespace == registry.namespace


def test_find_returns_none_when_absent(tmp_path: Path) -> None:
    assert IdRegistry.find(start=tmp_path) is None


def test_resolve_registry_explicit_file(tmp_path: Path) -> None:
    registry = IdRegistry.new("proj", path=tmp_path / "custom-ids.json")
    registry.save()
    resolved = resolve_registry(tmp_path, "custom-ids.json")
    assert resolved is not None
    assert resolved.namespace == registry.namespace


def test_resolve_registry_missing_explicit_file_degrades_to_none(
    tmp_path: Path,
) -> None:
    assert resolve_registry(tmp_path, "no-such-ids.json") is None


# ---------------------------------------------------------------------------
# import_sbom
# ---------------------------------------------------------------------------


def _write_sample_sbom(path: Path) -> dict[str, str]:
    """Write a small SPDX 3 SBOM; return the ids it hands out."""
    namespace = "https://spdx.org/spdxdocs/sample-abc123"
    ci = spdx3.CreationInfo(
        specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    agent = spdx3.SoftwareAgent(
        spdxId=f"{namespace}#SoftwareAgent-1", name="Pitloom", creationInfo=ci
    )
    ci.createdBy = [f"{namespace}#SoftwareAgent-1"]

    file_hash = _sha256(b"train data\n")
    dataset = spdx3.dataset_DatasetPackage(
        spdxId=f"{namespace}#File-7",
        name="data/processed/train.txt",
        creationInfo=ci,
        verifiedUsing=[
            spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=file_hash)
        ],
    )
    dataset.dataset_datasetType = [spdx3.dataset_DatasetType.text]
    script_hash = _sha256(b"train code\n")
    script = spdx3.software_File(
        spdxId=f"{namespace}#File-3",
        name="src/pkg/train.py",
        creationInfo=ci,
        verifiedUsing=[
            spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=script_hash)
        ],
    )
    # A file without any hash: must be skipped on import.
    hashless = spdx3.software_File(
        spdxId=f"{namespace}#File-9", name="src/pkg/nohash.py", creationInfo=ci
    )
    model = spdx3.ai_AIPackage(
        spdxId=f"{namespace}#AIPackage-1", name="sentimentdemo", creationInfo=ci
    )
    sbom = spdx3.software_Sbom(
        spdxId=f"{namespace}#Sbom-1", creationInfo=ci, rootElement=[model.spdxId]
    )
    doc = spdx3.SpdxDocument(
        spdxId=namespace, creationInfo=ci, rootElement=[sbom.spdxId]
    )

    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(ci)
    exporter.add_agent(agent)
    exporter.add_package(dataset)
    exporter.add_file(script)
    exporter.add_file(hashless)
    exporter.add_package(model)
    exporter.add_sbom(sbom)
    exporter.add_document(doc)
    path.write_text(exporter.to_json(), encoding="utf-8")

    return {
        "namespace": namespace,
        "dataset_id": f"{namespace}#File-7",
        "dataset_hash": file_hash,
        "script_id": f"{namespace}#File-3",
        "script_hash": script_hash,
        "model_id": f"{namespace}#AIPackage-1",
    }


def test_import_sbom_harvests_files_and_entities(tmp_path: Path) -> None:
    sbom_path = tmp_path / "sample.spdx3.json"
    ids = _write_sample_sbom(sbom_path)

    registry = IdRegistry.new("proj")
    registry.import_sbom(sbom_path)

    # dataset + script harvested into files, keyed by name, hash preserved
    assert registry.files["data/processed/train.txt"] == FileEntry(
        spdx_id=ids["dataset_id"], sha256=ids["dataset_hash"]
    )
    assert registry.files["src/pkg/train.py"] == FileEntry(
        spdx_id=ids["script_id"], sha256=ids["script_hash"]
    )
    # hashless file skipped
    assert "src/pkg/nohash.py" not in registry.files
    # AIPackage harvested into entities
    assert registry.entities["sentimentdemo"] == EntityEntry(
        type="ai_AIPackage", spdx_id=ids["model_id"]
    )


def test_import_sbom_adopts_namespace_when_registry_empty(tmp_path: Path) -> None:
    sbom_path = tmp_path / "sample.spdx3.json"
    ids = _write_sample_sbom(sbom_path)

    registry = IdRegistry.new("proj")
    registry.import_sbom(sbom_path)
    assert registry.namespace == ids["namespace"]


def test_import_sbom_keeps_namespace_when_registry_nonempty(tmp_path: Path) -> None:
    sbom_path = tmp_path / "sample.spdx3.json"
    _write_sample_sbom(sbom_path)

    registry = IdRegistry(
        namespace="https://spdx.org/spdxdocs/mine-1",
        files={
            "kept.txt": FileEntry(
                spdx_id="https://spdx.org/spdxdocs/mine-1#File-1", sha256="00" * 32
            )
        },
    )
    registry.import_sbom(sbom_path)
    assert registry.namespace == "https://spdx.org/spdxdocs/mine-1"
    assert "kept.txt" in registry.files


# ---------------------------------------------------------------------------
# register_* invariants
# ---------------------------------------------------------------------------


def test_mint_never_reuses_superseded_ids() -> None:
    registry = IdRegistry(namespace="https://spdx.org/spdxdocs/x-1")
    first = registry.register_file("a.txt", "11" * 32)
    # Content change replaces the entry with a fresh id...
    second = registry.register_file("a.txt", "22" * 32)
    assert first != second
    # ...and a further new file must not collide with either.
    third = registry.register_file("b.txt", "33" * 32)
    assert third not in (first, second)


def test_register_entity_reuses_existing_id() -> None:
    registry = IdRegistry(namespace="https://spdx.org/spdxdocs/x-1")
    first = registry.register_entity("model", "ai_AIPackage")
    second = registry.register_entity("model", "ai_AIPackage")
    assert first == second


# ---------------------------------------------------------------------------
# `pitloom ids generate --entity` CLI flag
# ---------------------------------------------------------------------------


def test_ids_generate_cli_entity_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--entity NAME[:TYPE]` registers entities up front, before the model
    file exists, so loom.set_model() can already share the id."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "raw.txt").write_text("raw\n")
    monkeypatch.chdir(tmp_path)

    parser = _build_parser()
    args = parser.parse_args(
        [
            "ids",
            "generate",
            "data",
            "--entity",
            "sentimentdemo",
            "--entity",
            "other:dataset_DatasetPackage",
        ]
    )
    exit_code = _run_ids_cli(args)
    assert exit_code == 0

    registry = IdRegistry.load(tmp_path / "loom-ids.json")
    assert registry.entities["sentimentdemo"].type == "ai_AIPackage"
    assert registry.entities["sentimentdemo"].spdx_id.endswith("#AIPackage-1")
    assert registry.entities["other"].type == "dataset_DatasetPackage"
    assert "data/raw.txt" in registry.files
