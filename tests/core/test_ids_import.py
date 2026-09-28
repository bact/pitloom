# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.id_registry import functionality."""

# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=too-few-public-methods

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.id_registry import EntityEntry, FileEntry, IdRegistry
from pitloom.id_registry._harvest import _import_sbom_element
from pitloom.id_registry._types import _entity_key
from tests.ids_shared import (
    _write_sample_sbom,
    _write_sample_sbom_without_document,
)


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
    # AIPackage harvested into entities
    assert registry.entities[("ai_AIPackage", "sentimentdemo")] == EntityEntry(
        spdx_id=ids["model_id"]
    )


def test_import_sbom_harvests_any_named_element_as_entity(tmp_path: Path) -> None:
    """Any element with a name and spdxId is importable, typed by its own
    SPDX 3 compact type. A hash-less File also falls back here instead of
    being dropped entirely."""
    sbom_path = tmp_path / "sample.spdx3.json"
    ids = _write_sample_sbom(sbom_path)

    registry = IdRegistry.new("proj")
    registry.import_sbom(sbom_path)

    # A software_Package.
    assert registry.entities[("software_Package", "requests")] == EntityEntry(
        spdx_id=ids["dep_package_id"]
    )
    # A hash-less software_File: not dropped, keyed as an entity instead.
    assert "src/pkg/nohash.py" not in registry.files
    assert registry.entities[("software_File", "src/pkg/nohash.py")] == EntityEntry(
        spdx_id=ids["hashless_id"]
    )
    # Even a creator Agent, typed by its own compact type.
    assert registry.entities[("SoftwareAgent", "Pitloom")] == EntityEntry(
        spdx_id=ids["agent_id"]
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


def test_import_sbom_no_document_keeps_minted_namespace(tmp_path: Path) -> None:
    """When no SpdxDocument element is present, a fresh registry's own
    freshly-minted namespace is left untouched (the harvesting loop runs
    to completion without ever finding a namespace to adopt)."""
    sbom_path = tmp_path / "sample.spdx3.json"
    _write_sample_sbom_without_document(sbom_path)

    registry = IdRegistry.new("proj")
    original_namespace = registry.namespace

    registry.import_sbom(sbom_path)

    assert registry.namespace == original_namespace
    assert registry.has_entity_named("nodoc-model")


def test_import_sbom_empty_elements() -> None:
    registry = IdRegistry.new("test")

    # We can fake the deserialized set and call _import_sbom_element

    class DummyElement:
        name = "test"
        spdxId = "http://test"

        def get_compact_type(self) -> Any:
            return "object"

    _import_sbom_element(registry, DummyElement())
    assert not registry.has_entity_named("test")

    class DummyElement2:
        name = "test"
        spdxId = "http://test"

        def get_compact_type(self) -> Any:
            return None

    _import_sbom_element(registry, DummyElement2())
    assert ("DummyElement2", "test") in registry.entities

    class DummyElement3:
        name = "test"
        # A different id from DummyElement2's -- this test is about
        # (type, name) keying preventing an *overwrite*, not about the
        # one-id-per-key invariant (see test_harvest_drops_stale_key_...
        # in test_ids_core.py for that), so the two ids here must differ
        # or the second harvest would legitimately release the first.
        spdxId = "http://test2"
        # no get_compact_type, but class name fallback

    _import_sbom_element(registry, DummyElement3())
    # Different compact type, same name -- both entries survive
    # independently (the exact overwrite hazard (type, name) keying fixes).
    assert ("DummyElement2", "test") in registry.entities
    assert ("DummyElement3", "test") in registry.entities


_CI = spdx3.CreationInfo(
    specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
)


def _hashed_file(name: str, spdx_id: str, sha256: str) -> spdx3.software_File:
    return spdx3.software_File(
        spdxId=spdx_id,
        name=name,
        creationInfo=_CI,
        verifiedUsing=[
            spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=sha256)
        ],
    )


def test_harvest_file_repointed_then_old_id_claimed_keeps_both() -> None:
    """A key moved to a new id no longer holds its old id: a later element
    claiming the old id must not release the moved key."""
    registry = IdRegistry.new("p")
    ns = registry.namespace
    registry.files["a.py"] = FileEntry(spdx_id=f"{ns}#File-2", sha256="1" * 64)
    object_set = spdx3.SHACLObjectSet()
    object_set.add(_hashed_file("a.py", f"{ns}#File-1", "1" * 64))
    object_set.add(_hashed_file("b.py", f"{ns}#File-2", "2" * 64))

    registry.harvest(object_set)

    assert registry.files["a.py"].spdx_id == f"{ns}#File-1"
    assert registry.files["b.py"].spdx_id == f"{ns}#File-2"


def test_harvest_entity_repointed_then_old_id_claimed_keeps_both() -> None:
    registry = IdRegistry.new("p")
    ns = registry.namespace
    registry.entities[_entity_key("m", "ai_AIPackage")] = EntityEntry(
        spdx_id=f"{ns}#AIPackage-2"
    )
    object_set = spdx3.SHACLObjectSet()
    object_set.add(
        spdx3.ai_AIPackage(spdxId=f"{ns}#AIPackage-1", name="m", creationInfo=_CI)
    )
    object_set.add(
        spdx3.ai_AIPackage(spdxId=f"{ns}#AIPackage-2", name="n", creationInfo=_CI)
    )

    registry.harvest(object_set)

    assert registry.lookup_entity("m", "ai_AIPackage") == f"{ns}#AIPackage-1"
    assert registry.lookup_entity("n", "ai_AIPackage") == f"{ns}#AIPackage-2"
