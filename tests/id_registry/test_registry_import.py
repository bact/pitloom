# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``IdRegistry.import_sbom`` and ``pitloom id import``.

See also: test_registry.py, test_registry_harvest.py,
test_registry_generate.py, shared.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    PACKAGE_TYPE,
    IdRegistry,
    IdRegistrySession,
    RegistryEntry,
)
from tests.cli.shared import SAFETENSORS_FIXTURE
from tests.id_registry.shared import (
    _sha256,
    _write_sample_sbom,
    _write_sample_sbom_without_document,
)
from tests.id_registry.surfaces_base import _run_cli
from tests.registry_helpers import make_registry

_IMPORTED = "https://spdx.org/spdxdocs/imported-1"
_CI = spdx3.CreationInfo(
    specVersion="3.0.1",
    created=datetime(2026, 1, 1, tzinfo=timezone.utc),
    createdBy=[f"{_IMPORTED}#SoftwareAgent-1"],
)


def test_import_sbom_records_every_element_with_its_type(tmp_path: Path) -> None:
    """Each named element is keyed by its own type, with its hash or none:
    nothing is filed by shape."""
    sbom_path = tmp_path / "sample.spdx3.json"
    ids = _write_sample_sbom(sbom_path)

    registry = IdRegistry.new("proj")
    registry.import_sbom(sbom_path)

    # No lookup gates a dataset on content: its hash is not recorded.
    assert registry.get(DATASET_PACKAGE_TYPE, "data/processed/train.txt") == (
        RegistryEntry(ids["dataset_id"])
    )
    assert registry.get(FILE_TYPE, "src/pkg/train.py") == RegistryEntry(
        ids["script_id"], ids["script_hash"]
    )
    assert registry.get(FILE_TYPE, "src/pkg/nohash.py") == RegistryEntry(
        ids["hashless_id"]
    )
    assert registry.get(AI_PACKAGE_TYPE, "sentimentdemo") == RegistryEntry(
        ids["model_id"]
    )
    assert registry.get(PACKAGE_TYPE, "requests") == RegistryEntry(
        ids["dep_package_id"]
    )
    assert registry.get("SoftwareAgent", "Pitloom") == RegistryEntry(ids["agent_id"])
    # The dataset is not reachable as a file: lookups never cross types.
    assert registry.get(FILE_TYPE, "data/processed/train.txt") is None


def test_import_sbom_adopts_namespace_when_registry_empty(tmp_path: Path) -> None:
    sbom_path = tmp_path / "sample.spdx3.json"
    ids = _write_sample_sbom(sbom_path)

    registry = IdRegistry.new("proj")
    registry.import_sbom(sbom_path)
    assert registry.namespace == ids["namespace"]


def test_import_sbom_keeps_namespace_when_registry_nonempty(tmp_path: Path) -> None:
    sbom_path = tmp_path / "sample.spdx3.json"
    _write_sample_sbom(sbom_path)
    mine = "https://spdx.org/spdxdocs/mine-1"
    registry = make_registry(
        {(FILE_TYPE, "kept.txt"): (f"{mine}#File-1", "00" * 32)}, namespace=mine
    )

    registry.import_sbom(sbom_path)

    assert registry.namespace == mine
    assert registry.get(FILE_TYPE, "kept.txt") is not None


def test_import_sbom_no_document_keeps_minted_namespace(tmp_path: Path) -> None:
    sbom_path = tmp_path / "sample.spdx3.json"
    _write_sample_sbom_without_document(sbom_path)

    registry = IdRegistry.new("proj")
    original_namespace = registry.namespace

    registry.import_sbom(sbom_path)

    assert registry.namespace == original_namespace
    assert registry.has_name("nodoc-model")


def _write_sbom(
    path: Path,
    *elements: spdx3.software_Package | spdx3.software_File,
    document_id: str = _IMPORTED,
) -> None:
    namespace = _IMPORTED
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(_CI)
    exporter.add_agent(
        spdx3.SoftwareAgent(
            spdxId=f"{namespace}#SoftwareAgent-1", name="Pitloom", creationInfo=_CI
        )
    )
    for element in elements:
        if isinstance(element, spdx3.software_File):
            exporter.add_file(element)
        else:
            exporter.add_package(element)
    exporter.add_document(
        spdx3.SpdxDocument(
            spdxId=document_id,
            creationInfo=_CI,
            rootElement=[str(elements[0].spdxId)],
        )
    )
    path.write_text(exporter.to_json(), encoding="utf-8")


@pytest.mark.parametrize(
    ("document_id", "adopted"),
    [
        (_IMPORTED, True),
        ("urn:uuid:0b6e4c0e-8a3a-4c39-9d1e-3f1b4c2a7d10", True),
        (f"{_IMPORTED}#SPDXRef-DOCUMENT", False),
        ("https://example.org/a b", False),
    ],
    ids=["https", "urn", "fragment", "space"],
)
def test_import_sbom_adopts_only_a_namespace_iri(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, document_id: str, adopted: bool
) -> None:
    """A document id that cannot be a namespace (``...#x`` would make ids
    ``...#x#File-1``) is not adopted: one ``WARNING:`` naming why."""
    sbom_path = tmp_path / "doc.spdx3.json"
    _write_sbom(
        sbom_path,
        spdx3.software_Package(
            spdxId=f"{_IMPORTED}#Package-1", name="p", creationInfo=_CI
        ),
        document_id=document_id,
    )
    registry = IdRegistry.new("proj")
    minted = registry.namespace

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        registry.import_sbom(sbom_path)

    assert registry.namespace == (document_id if adopted else minted)
    warnings = [r.getMessage() for r in caplog.records]
    assert len(warnings) == (0 if adopted else 1)
    if warnings:
        assert warnings[0].startswith("ID registry: not adopting the namespace")
        assert repr(document_id) in warnings[0]


def test_import_sbom_returns_an_ambiguous_file_path(tmp_path: Path) -> None:
    """I5: two files under one path are skipped, and returned."""
    ns = _IMPORTED
    sbom_path = tmp_path / "two.spdx3.json"
    hashes = ["1" * 64, "2" * 64]
    _write_sbom(
        sbom_path,
        *(
            spdx3.software_File(
                spdxId=f"{ns}#File-{n}",
                name="lib/a.so",
                creationInfo=_CI,
                verifiedUsing=[
                    spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=sha)
                ],
            )
            for n, sha in enumerate(hashes, 1)
        ),
    )
    registry = IdRegistry.new("r")

    skipped = registry.import_sbom(sbom_path)

    assert skipped == {(FILE_TYPE, "lib/a.so")}
    assert registry.get(FILE_TYPE, "lib/a.so") is None


# --- headline regression: a hashed AIPackage survives `id import` ------


def _hashed_model(name: str, spdx_id: str, sha256: str) -> spdx3.ai_AIPackage:
    return spdx3.ai_AIPackage(
        spdxId=spdx_id,
        name=name,
        creationInfo=_CI,
        verifiedUsing=[
            spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=sha256)
        ],
    )


def test_import_keeps_a_hashed_ai_package_for_a_typed_lookup(tmp_path: Path) -> None:
    sha = _sha256(SAFETENSORS_FIXTURE.read_bytes())
    model_id = f"{_IMPORTED}#AIPackage-1"
    sbom_path = tmp_path / "model.spdx3.json"
    _write_sbom(sbom_path, _hashed_model(SAFETENSORS_FIXTURE.stem, model_id, sha))
    path = tmp_path / "registry.json"
    registry = IdRegistry.new("r")
    registry.import_sbom(sbom_path)
    registry.save(path)

    reloaded = IdRegistry.load(path)
    session = IdRegistrySession(reloaded)

    assert reloaded.get(AI_PACKAGE_TYPE, SAFETENSORS_FIXTURE.stem) == RegistryEntry(
        model_id, sha
    )
    assert reloaded.lookup(AI_PACKAGE_TYPE, [SAFETENSORS_FIXTURE.stem]) == model_id
    assert (
        session.lookup_id(
            "model", AI_PACKAGE_TYPE, [SAFETENSORS_FIXTURE.stem], sha256=sha.upper()
        )
        == model_id
    )


def test_cli_import_then_model_reuses_a_hashed_ai_package_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end, through the CLI only: an SBOM whose AIPackage carries a
    hash is imported, then ``pitloom model`` looks the model up by stem."""
    sha = _sha256(SAFETENSORS_FIXTURE.read_bytes())
    model_id = f"{_IMPORTED}#AIPackage-1"
    sbom_path = tmp_path / "model.spdx3.json"
    _write_sbom(sbom_path, _hashed_model(SAFETENSORS_FIXTURE.stem, model_id, sha))
    registry = tmp_path / "registry.json"
    out = tmp_path / "out.spdx3.json"

    assert (
        _run_cli(monkeypatch, ["id", "import", str(sbom_path), "-o", str(registry)])
        == 0
    )
    argv = ["model", str(SAFETENSORS_FIXTURE), "-o", str(out)]
    assert _run_cli(monkeypatch, [*argv, "--id-registry", str(registry)]) == 0

    graph = json.loads(out.read_text(encoding="utf-8"))["@graph"]
    assert [e["spdxId"] for e in graph if e["type"] == "ai_AIPackage"] == [model_id]
