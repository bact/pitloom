# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared utilities for pitloom.ids tests."""

# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=too-few-public-methods

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.export.spdx3_json import Spdx3JsonExporter


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_bytes(b"print(1)\n")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.txt").write_bytes(b"hello\n")
    return tmp_path


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
    # A file without any hash: no content to gate on, so it must fall back
    # to a name-keyed entity rather than being dropped.
    hashless = spdx3.software_File(
        spdxId=f"{namespace}#File-9", name="src/pkg/nohash.py", creationInfo=ci
    )
    model = spdx3.ai_AIPackage(
        spdxId=f"{namespace}#AIPackage-1", name="sentimentdemo", creationInfo=ci
    )
    # A dependency package -- not one of the three types the old hardcoded
    # allowlist handled, but it has a name and spdxId like anything else.
    dep_package = spdx3.software_Package(
        spdxId=f"{namespace}#Package-2", name="requests", creationInfo=ci
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
    exporter.add_package(dep_package)
    exporter.add_sbom(sbom)
    exporter.add_document(doc)
    path.write_text(exporter.to_json(), encoding="utf-8")

    return {
        "namespace": namespace,
        "dataset_id": f"{namespace}#File-7",
        "dataset_hash": file_hash,
        "script_id": f"{namespace}#File-3",
        "script_hash": script_hash,
        "hashless_id": f"{namespace}#File-9",
        "model_id": f"{namespace}#AIPackage-1",
        "dep_package_id": f"{namespace}#Package-2",
        "agent_id": f"{namespace}#SoftwareAgent-1",
    }


def _write_sample_sbom_without_document(path: Path) -> dict[str, str]:
    """Write a small SPDX 3 SBOM with no ``SpdxDocument`` element.

    Used to exercise the "no SpdxDocument found while harvesting a fresh
    registry's namespace" fall-through in :meth:`pitloom.ids.IdRegistry.import_sbom`.
    """
    namespace = "https://spdx.org/spdxdocs/sample-nodoc"
    ci = spdx3.CreationInfo(
        specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    agent = spdx3.SoftwareAgent(
        spdxId=f"{namespace}#SoftwareAgent-1", name="Pitloom", creationInfo=ci
    )
    ci.createdBy = [f"{namespace}#SoftwareAgent-1"]
    model = spdx3.ai_AIPackage(
        spdxId=f"{namespace}#AIPackage-1", name="nodoc-model", creationInfo=ci
    )

    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(ci)
    exporter.add_agent(agent)
    exporter.add_package(model)
    path.write_text(exporter.to_json(), encoding="utf-8")

    return {
        "namespace": namespace,
        "model_id": f"{namespace}#AIPackage-1",
    }
