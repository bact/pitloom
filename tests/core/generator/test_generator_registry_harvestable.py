# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which elements run auto-harvest writes back (D15): a hashed
``ai_AIPackage`` yes (under its file's key), an unhashed one no, a
``dataset_DatasetPackage`` never; a loom fragment's ``software_File``
merged into a project SBOM yes.

See also: tests/core/generator/test_generator_registry_sync.py (auto-sync
through every generator), tests/core/test_loom_model.py (loom's own write).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom import loom
from pitloom.assemble import generate_project_sbom
from pitloom.assemble._generators_shared import _harvestable
from pitloom.core.config import FragmentConfig, PitloomConfig
from pitloom.export.spdx3_json import sha256_hash
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    IdRegistry,
)
from pitloom.id_registry._ambiguous import MODEL_NOT_RECORDED_INFO

from ..conftest import _write_smoke_project

_CI = spdx3.CreationInfo(
    specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
)
_ID = "https://spdx.org/spdxdocs/x-1#E-1"


@pytest.mark.parametrize(
    ("element_type", "hashed", "harvested"),
    [
        (spdx3.ai_AIPackage, True, True),
        (spdx3.ai_AIPackage, False, False),
        (spdx3.dataset_DatasetPackage, True, False),
        (spdx3.dataset_DatasetPackage, False, False),
        (spdx3.software_File, True, True),
        (spdx3.software_Package, False, True),
    ],
    ids=["ai-hashed", "ai", "dataset-hashed", "dataset", "file", "package"],
)
def test_harvestable(element_type: type, hashed: bool, harvested: bool) -> None:
    element = element_type(spdxId=_ID, name="x", creationInfo=_CI)
    if hashed:
        element.verifiedUsing = [sha256_hash("a" * 64)]
    assert _harvestable(element) is harvested


def test_a_merged_loom_fragment_is_harvested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A loom fragment merged into a project SBOM: its dataset's file is
    written back; the dataset package is not, nor its hashed model, whose
    file is not in the document (one INFO): a name key would outlive a
    retrain."""
    _write_smoke_project(tmp_path)
    (tmp_path / "data.txt").write_bytes(b"rows\n")
    (tmp_path / "m.bin").write_bytes(b"weights")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    with loom.run(tmp_path / "frag.json"):
        loom.set_model("m", path="m.bin")
        loom.add_dataset("data.txt")
    registry = tmp_path / "reg.json"
    IdRegistry.new("smoke-project", path=registry).save()

    with caplog.at_level(logging.INFO, logger="pitloom"):
        generate_project_sbom(
            tmp_path,
            id_registry=registry,
            pitloom_config=PitloomConfig(fragments=[FragmentConfig(path="frag.json")]),
        )

    saved = IdRegistry.load(registry)
    assert saved.get(AI_PACKAGE_TYPE, "m") is None
    assert caplog.messages.count(MODEL_NOT_RECORDED_INFO % "m") == 1
    held = saved.get(FILE_TYPE, "data.txt")
    assert held is not None and held.sha256 is not None
    assert not [key for key in saved.elements if key[0] == DATASET_PACKAGE_TYPE]
