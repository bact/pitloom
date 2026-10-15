# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Originators (``originatedBy``) read from a PT2 Archive's ``extra/author``.

See also: :mod:`tests.extract.ai_model.test_pytorch_pt2`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.core.model_originators import ORIGINATORS_PROVENANCE_KEY
from pitloom.extract.ai_model.pytorch_pt2 import read_pytorch_pt2

from .test_pytorch_pt2 import _make_pt2_zip

FIXTURE = (
    Path(__file__).parents[2] / "fixtures" / "aimodels" / "pytorch_pt2"
    / "example-model.pt2"
)  # fmt: skip


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"Jane", ["Jane"]),
        (b"  Jane Doe \n", ["Jane Doe"]),
        (b"Doe, Jane", ["Doe, Jane"]),
        (b"A|B", ["A|B"]),
        (b"A\x07B\nC", ["A\x07B\nC"]),
        (b"  \n", []),
        (None, []),
    ],
    ids=["plain", "stripped", "comma", "pipe", "control", "blank", "absent"],
)
def test_originators_from_extra_author(
    tmp_path: Path, raw: bytes | None, expected: list[str]
) -> None:
    files = {"mdl/extra/name": b"m"}
    if raw is not None:
        files["mdl/extra/author"] = raw
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip(files))
    meta = read_pytorch_pt2(model_file)

    assert meta.originators == expected
    if expected:
        assert (
            meta.provenance[ORIGINATORS_PROVENANCE_KEY]
            == (meta.provenance["properties.author"])
        )
        assert meta.provenance[ORIGINATORS_PROVENANCE_KEY] == (
            "Source: model.pt2 | Field: extra/author"
        )
        assert meta.properties["author"] == expected[0]
    else:
        assert ORIGINATORS_PROVENANCE_KEY not in meta.provenance
        assert "author" not in meta.properties


def test_originators_from_example_fixture() -> None:
    meta = read_pytorch_pt2(FIXTURE)
    assert meta.originators == ["Pitloom"]
    assert meta.properties["author"] == "Pitloom"
    assert meta.provenance[ORIGINATORS_PROVENANCE_KEY] == (
        "Source: example-model.pt2 | Field: extra/author"
    )
