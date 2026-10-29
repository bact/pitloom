# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""G7 ``DP-007`` (a dataset's statistical properties) reads
``dataset_datasetSize`` (bytes) or ``dataset_knownBias``. A Croissant record
count is neither, so it must not satisfy the rule.

See also: tests/conformance/g7ai_shared.py, test_g7ai_outcomes.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom.core.dataset_metadata import DatasetMetadata
from pitloom.extract.dataset.croissant import read_croissant
from tests.conformance.g7ai_shared import library_sbom, outcomes

_RULE = "BOM-G7AI2026-DP-007"


def _croissant_count_only(tmp_path: Path) -> DatasetMetadata:
    path = tmp_path / "ds.json"
    path.write_text(
        json.dumps({"name": "corpus", "totalItems": 5000, "recordSet": []}),
        encoding="utf-8",
    )
    return read_croissant(path)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("bytes", "present"), ("bias", "present"), ("count", "missing")],
)
def test_dp_007_is_satisfied_by_bytes_or_bias_not_by_a_count(
    tmp_path: Path, kind: str, expected: str
) -> None:
    datasets = {
        "bytes": DatasetMetadata(name="corpus", byte_size=1000),
        "bias": DatasetMetadata(name="corpus", known_bias=["skewed to news"]),
        "count": _croissant_count_only(tmp_path),
    }
    sbom = tmp_path / "m.spdx3.json"
    sbom.write_text(library_sbom(datasets[kind]), encoding="utf-8")
    assert outcomes(sbom)[_RULE] == expected
