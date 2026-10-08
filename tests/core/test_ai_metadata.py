# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the name helpers of :class:`pitloom.core.ai_metadata.AiModelMetadata`
and for :func:`pitloom.core.ai_metadata.source_metadata`.

See also: :mod:`tests.assemble.test_assemble_ai` (the resolved name in the SBOM)
and :mod:`tests.assemble.test_source_metadata_annotation` (every reader's
annotation).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import pytest

from pitloom.core.ai_metadata import (
    FILE_NAME_STEM_PROVENANCE,
    SOURCE_METADATA_MAX_DEPTH,
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
    source_metadata,
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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, "True"),
        (9.999999974752427e-07, "9.999999974752427e-07"),
        (2**63 + 1, "9223372036854775809"),
        (("a", 1), ["a", "1"]),
        ({"out": [0.5, False, None, True]}, {"out": ["0.5", "false", "null", "true"]}),
        ({1: "x"}, {"1": "x"}),
        ([], []),
        ([float("nan"), 2**63 + 1, b"x"], ["NaN", "9223372036854775809", "b'x'"]),
    ],
    ids=["bool", "float", "big-int", "tuple", "nested", "int-key", "empty", "odd"],
)
def test_source_metadata_keeps_collections_and_makes_scalars_text(
    value: object, expected: object
) -> None:
    """A top-level scalar is ``str()``, the text of ``properties``; one inside
    a collection is spelt as JSON spells it, as the collection's JSON text
    in ``properties`` is."""
    assert source_metadata({"k": value}) == {"k": expected}


def test_source_metadata_leaves_out_a_key_without_a_value() -> None:
    assert source_metadata({"a": None, "b": "1"}, {"c": None}) == {"b": "1"}


def _nested(depth: int) -> object:
    value: object = "x"
    for _ in range(depth):
        value = [value]
    return value


@pytest.mark.parametrize(
    "depth",
    [SOURCE_METADATA_MAX_DEPTH, SOURCE_METADATA_MAX_DEPTH + 1, 1000, 5000],
    ids=["at-bound", "over-bound", "1000", "5000"],
)
def test_source_metadata_collapses_a_hostile_nesting(depth: int) -> None:
    """A nesting over the bound is cut to text, never a RecursionError."""
    value = source_metadata({"k": _nested(depth)})["k"]
    kept = 0
    while isinstance(value, list):
        assert len(value) == 1
        value, kept = value[0], kept + 1
    assert kept == min(depth, SOURCE_METADATA_MAX_DEPTH)
    assert isinstance(value, str)
    if depth == SOURCE_METADATA_MAX_DEPTH:
        assert value == "x"
    elif depth == SOURCE_METADATA_MAX_DEPTH + 1:
        assert value == '["x"]'
    else:  # JSON text, or a marker where even that nests too deeply
        assert value.strip("[]") == '"x"' or value == (
            f"<nested over {SOURCE_METADATA_MAX_DEPTH} levels>"
        )


def test_source_metadata_collection_keeps_its_place_in_the_text_map() -> None:
    properties = {"a": "1", "labels": '["x", "y"]', "b": "2"}
    merged = source_metadata(properties, {"labels": ("x", "y"), "extra": ["z"]})
    assert list(merged) == ["a", "labels", "b", "extra"]
    assert merged["labels"] == ["x", "y"]
    assert properties["labels"] == '["x", "y"]'  # the input is not changed
