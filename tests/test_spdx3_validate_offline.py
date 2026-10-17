# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for offline validation with the vendored SPDX model snapshot.

See also: tests/_spdx3_validate.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom.assemble import generate_model_sbom
from tests._spdx3_validate import SPDX_MODEL_DIR, assert_spdx3_valid, spdx3_errors

FIXTURES = Path(__file__).parent / "fixtures"
MODEL = FIXTURES / "aimodels" / "safetensors" / "phi-tiny-random.safetensors"


@pytest.fixture(name="sbom")
def _sbom(tmp_path: Path) -> Path:
    path = tmp_path / "model.spdx3.json"
    path.write_text(generate_model_sbom(str(MODEL), offline=True), encoding="utf-8")
    return path


def test_snapshot_dir_has_the_version_folder() -> None:
    assert (SPDX_MODEL_DIR / "v3.0.1" / "spdx-model.ttl").is_file()


def test_generated_sbom_is_valid_offline(sbom: Path) -> None:
    assert_spdx3_valid(sbom)


def test_invalid_sbom_reports_errors(sbom: Path, tmp_path: Path) -> None:
    doc = json.loads(sbom.read_text(encoding="utf-8"))
    package = next(e for e in doc["@graph"] if e["type"] == "ai_AIPackage")
    package["name"] = 42  # wrong type for a string property
    bad = tmp_path / "bad.spdx3.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    assert doc != json.loads(sbom.read_text(encoding="utf-8"))
    assert spdx3_errors(bad)
    with pytest.raises(AssertionError, match="spdx3-validate failed"):
        assert_spdx3_valid(bad)
