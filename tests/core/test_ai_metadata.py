# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the name helpers of :class:`pitloom.core.ai_metadata.AiModelMetadata`.

See also: :mod:`tests.assemble.test_assemble_ai` (the resolved name in the SBOM).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import pytest

from pitloom.core.ai_metadata import (
    FILE_NAME_STEM_PROVENANCE,
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
)


@pytest.mark.parametrize(
    ("name", "file_name", "expected", "from_stem"),
    [
        ("tiny-model", "deepcut.onnx", "tiny-model", False),
        (None, "deepcut.onnx", "deepcut", True),
        (None, "model.tar.gz", "model.tar", True),
        (None, None, "onnx", False),
        (None, "", "onnx", False),
        ("", "deepcut.onnx", "deepcut", True),
        ("  ", "deepcut.onnx", "deepcut", True),
        ("  tiny  ", "deepcut.onnx", "tiny", False),
    ],
)
def test_resolve_name_cascade(
    name: str | None, file_name: str | None, expected: str, from_stem: bool
) -> None:
    """Own name stripped, else file name stem (with its provenance), else
    format; the model itself is never changed."""
    model = AiModelMetadata(
        name=name,
        format_info=AiModelFormatInfo(
            file_name=file_name, model_format=AiModelFormat.ONNX
        ),
        provenance={"version": "Source: x.onnx | Field: model_version"},
    )
    before = dict(model.provenance)
    resolved, provenance = model.resolve_name()
    assert resolved == expected
    assert model.name == name  # the read value stays as read
    if from_stem:
        assert provenance["name"] == FILE_NAME_STEM_PROVENANCE
    else:
        assert "name" not in provenance
    assert provenance["version"] == before["version"]
    assert model.provenance == before  # the model's own map is not mutated
    provenance["probe"] = "x"  # a copy in every branch, never an alias
    assert "probe" not in model.provenance
    assert "probe" not in model.resolve_name()[1]


def test_format_fallback_drops_a_blank_names_provenance() -> None:
    """A reader that recorded provenance for a blank name cites nothing the
    SBOM shows once the format names the model."""
    model = AiModelMetadata(
        name="  ",
        format_info=AiModelFormatInfo(model_format=AiModelFormat.GGUF),
        provenance={"name": "Source: x.gguf | Field: general.name", "version": "v"},
    )
    assert model.resolve_name() == ("gguf", {"version": "v"})
    assert "name" in model.provenance  # the model's own map is unchanged
