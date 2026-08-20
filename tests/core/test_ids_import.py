# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.ids import functionality."""

# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=too-few-public-methods

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitloom.ids import (
    EntityEntry,
    FileEntry,
    IdRegistry,
    _import_sbom_element,
)
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
    assert registry.entities["sentimentdemo"] == EntityEntry(
        type="ai_AIPackage", spdx_id=ids["model_id"]
    )


def test_import_sbom_harvests_any_named_element_as_entity(tmp_path: Path) -> None:
    """Not just the historically-special-cased File/Dataset/AIPackage types
    -- any element with a name and spdxId is importable, typed by its own
    SPDX 3 compact type. A hash-less File also falls back here instead of
    being dropped entirely."""
    sbom_path = tmp_path / "sample.spdx3.json"
    ids = _write_sample_sbom(sbom_path)

    registry = IdRegistry.new("proj")
    registry.import_sbom(sbom_path)

    # A software_Package (not one of the old three hardcoded types).
    assert registry.entities["requests"] == EntityEntry(
        type="software_Package", spdx_id=ids["dep_package_id"]
    )
    # A hash-less software_File: not dropped, keyed as an entity instead.
    assert "src/pkg/nohash.py" not in registry.files
    assert registry.entities["src/pkg/nohash.py"] == EntityEntry(
        type="software_File", spdx_id=ids["hashless_id"]
    )
    # Even a creator Agent, typed by its own compact type.
    assert registry.entities["Pitloom"] == EntityEntry(
        type="SoftwareAgent", spdx_id=ids["agent_id"]
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
    assert "nodoc-model" in registry.entities


def test_import_sbom_empty_elements() -> None:
    registry = IdRegistry.new("test")

    # We can fake the deserialized set and call _import_sbom_element

    class DummyElement:
        name = "test"
        spdxId = "http://test"

        def get_compact_type(self) -> Any:
            return "object"

    _import_sbom_element(registry, DummyElement())
    assert "test" not in registry.entities

    class DummyElement2:
        name = "test"
        spdxId = "http://test"

        def get_compact_type(self) -> Any:
            return None

    _import_sbom_element(registry, DummyElement2())
    assert registry.entities["test"].type == "DummyElement2"

    class DummyElement3:
        name = "test"
        spdxId = "http://test"
        # no get_compact_type, but class name fallback

    _import_sbom_element(registry, DummyElement3())
    assert registry.entities["test"].type == "DummyElement3"
