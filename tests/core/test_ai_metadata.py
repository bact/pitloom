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

import ast
import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

import pitloom
from pitloom.core.ai_metadata import (
    FILE_NAME_STEM_PROVENANCE,
    MAX_MODEL_NAME_CHARS,
    MODEL_NAME_CUT_NOTE,
    SOURCE_METADATA_MAX_DEPTH,
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
    cap_model_name,
    record_scalar_property,
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


@pytest.mark.parametrize("own", [True, False], ids=["own-name", "stem"])
@pytest.mark.parametrize("extra", [-1, 0, 1, 2**20], ids=["1023", "1024", "1025", "1M"])
def test_resolve_name_caps_a_long_name(own: bool, extra: int) -> None:
    """A name or stem over the cap is cut to its start, ``...``, ``~`` and 8
    hex digits of the SHA-256 of the whole name, that many code points in
    all, and its provenance says so; ``name`` stays as read.
    The registry candidates and the label see the same cut name."""
    long = "\u0e01" * (MAX_MODEL_NAME_CHARS + extra)  # one code point, 3 bytes
    source = "Source: m.onnx | Field: graph.name"
    model = AiModelMetadata(
        name=f" {long} " if own else None,
        format_info=AiModelFormatInfo(
            file_name="m.onnx" if own else f"{long}.onnx",
            model_format=AiModelFormat.ONNX,
        ),
        provenance={"name": source} if own else {},
    )
    resolved, provenance = model.resolve_name()
    cut = extra > 0
    assert len(resolved) == min(len(long), MAX_MODEL_NAME_CHARS)
    digest = hashlib.sha256(long.encode()).hexdigest()[:8]
    expected = long[: MAX_MODEL_NAME_CHARS - 12] + f"...~{digest}" if cut else long
    assert resolved == expected
    assert (model.own_name if own else model.file_name_stem) == resolved
    assert model.name_cut_length() == (len(long) if cut else None)
    base = source if own else FILE_NAME_STEM_PROVENANCE
    assert provenance["name"] == base + (MODEL_NAME_CUT_NOTE if cut else "")
    assert model.name == (f" {long} " if own else None)
    assert model.provenance == ({"name": source} if own else {})


def test_two_long_names_sharing_their_cut_start_stay_different() -> None:
    """The digest covers the whole name: names differing only past the cut,
    or only in their last character, never share a cut name."""
    start = "a" * MAX_MODEL_NAME_CHARS
    names = {cap_model_name(start + tail) for tail in ("x", "y", "xy", "yx")}
    assert len(names) == 4
    assert {len(name) for name in names} == {MAX_MODEL_NAME_CHARS}
    assert cap_model_name(start + "x") == cap_model_name(start + "x")  # stable


def test_a_cut_name_without_provenance_gets_none() -> None:
    model = AiModelMetadata(name="x" * (MAX_MODEL_NAME_CHARS + 1))
    assert not model.resolve_name()[1]


@pytest.mark.parametrize(
    ("value", "expected", "value_type"),
    [
        (True, "true", "boolean"),
        (9.999999974752427e-07, "9.999999974752427e-7", "float"),
        (2**63 + 1, "9223372036854775809", "integer"),
        ("1.5", "1.5", None),
        (("a", 1), ["a", "1"], None),
        (
            {"out": [0.5, False, None, True, 1e-7]},
            {"out": ["0.5", "false", "null", "true", "1e-7"]},
            None,
        ),
        ({1: "x"}, {"1": "x"}, None),
        ([], [], None),
        (
            [float("nan"), float("-inf"), 2**63 + 1, b"x"],
            ["NaN", "-INF", "9223372036854775809", "b'x'"],
            None,
        ),
        (b"x", "b'x'", None),
        (Decimal("1.10"), "1.10", None),  # str(): no scalar_text spelling
    ],
    ids=[
        "bool",
        "float",
        "big-int",
        "str",
        "tuple",
        "nested",
        "int-key",
        "empty",
        "odd",
        "bytes",
        "decimal",
    ],
)
def test_source_metadata_keeps_collections_and_makes_scalars_text(
    value: object, expected: object, value_type: str | None
) -> None:
    """A scalar, top-level or inside a collection, is its ``scalar_text``
    (``None`` inside a collection ``null``); only a top-level non-string
    scalar is typed."""
    raw = source_metadata({"k": value})
    assert raw["raw_metadata"] == {"k": expected}
    assert raw["raw_metadata_types"] == ({"k": value_type} if value_type else {})


def test_source_metadata_leaves_out_a_key_without_a_value() -> None:
    raw = source_metadata({"a": None, "b": "1"}, {"c": None})
    assert raw == {"raw_metadata": {"b": "1"}, "raw_metadata_types": {}}


def test_source_metadata_types_a_native_scalar_held_as_text() -> None:
    """A native scalar in the second map types the key its text holds."""
    properties: dict[str, str] = {"n": "", "s": "x"}
    natives: dict[str, object] = {}
    record_scalar_property(properties, natives, "n", 25)
    assert properties == {"n": "25", "s": "x"}
    raw = source_metadata(properties, natives)
    assert raw == {
        "raw_metadata": {"n": "25", "s": "x"},
        "raw_metadata_types": {"n": "integer"},
    }


def _nested(depth: int, leaf: object = "x") -> object:
    value: object = leaf
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
    value = source_metadata({"k": _nested(depth)})["raw_metadata"]["k"]
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


def test_a_collection_over_the_bound_is_its_canonical_json_text() -> None:
    leaf = {"b": [1, 1e-7, float("nan")], "a": True}
    value = source_metadata({"k": _nested(SOURCE_METADATA_MAX_DEPTH, leaf)})
    text = value["raw_metadata"]["k"]
    for _ in range(SOURCE_METADATA_MAX_DEPTH):
        text = text[0]
    assert text == '{"a":true,"b":[1,1e-7,"NaN"]}'


def test_source_metadata_collection_keeps_its_place_in_the_text_map() -> None:
    properties = {"a": "1", "labels": '["x", "y"]', "b": "2"}
    merged = source_metadata(properties, {"labels": ("x", "y"), "extra": ["z"]})[
        "raw_metadata"
    ]
    assert list(merged) == ["a", "labels", "b", "extra"]
    assert merged["labels"] == ["x", "y"]
    assert properties["labels"] == '["x", "y"]'  # the input is not changed


_SOURCE_FIELDS = ("raw_metadata", "raw_metadata_types")


def test_no_model_metadata_call_sets_the_source_metadata_fields_by_hand() -> None:
    """``raw_metadata`` and ``raw_metadata_types`` come only from splatting
    :func:`source_metadata`, so the two can never drift apart."""
    root = Path(pitloom.__file__).parent
    calls = [
        (path.relative_to(root).as_posix(), node)
        for path in root.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_bytes()))
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", getattr(node.func, "attr", None))
        == "AiModelMetadata"
    ]
    splatted = [
        where for where, node in calls if any(kw.arg is None for kw in node.keywords)
    ]
    assert len(splatted) >= 10  # every reader; the scan is not vacuous
    by_hand = [
        f"{where}:{node.lineno}"
        for where, node in calls
        if any(kw.arg in _SOURCE_FIELDS for kw in node.keywords)
    ]
    assert not by_hand


# The one module that may assign them after construction: the entry cap,
# which keeps the two in step (cap_entries).
_SOURCE_FIELD_STORES_ALLOWED = frozenset({"extract/ai_model/limits.py"})


def test_no_code_assigns_the_source_metadata_fields_by_hand() -> None:
    """Nor does any code set them later (``meta.raw_metadata = ...``),
    outside the entry cap."""
    root = Path(pitloom.__file__).parent
    stores = [
        (path.relative_to(root).as_posix(), node.lineno)
        for path in root.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_bytes()))
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ast.Store)
        and node.attr in _SOURCE_FIELDS
    ]
    assert {where for where, _ in stores} == _SOURCE_FIELD_STORES_ALLOWED
