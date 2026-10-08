# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""GGUF scalars as text: a ``FLOAT32`` is spelt as the float32's own
shortest decimal, a ``FLOAT64`` as stored, a ``BOOL`` ``true``/``false``,
the same in ``properties``, ``ai_hyperparameter`` and the artifact-metadata
annotation, which types each key in ``valueTypes``.

See also: :mod:`tests.core.test_scalar_text` (the spelling) and
:mod:`tests.assemble.test_source_metadata_annotation` (every format).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_model_sbom
from pitloom.extract.ai_model import read_ai_model
from tests.extract.ai_model.gguf_builders import (
    BOOL,
    FLOAT32,
    FLOAT64,
    STRING,
    gguf_file,
    kv,
    string,
)

pytest.importorskip("gguf")

_HYPER_KEY = "llama.attention.layer_norm_rms_epsilon"  # a hyperparameter key


def _value(vtype: int, value: float) -> bytes:
    if vtype == FLOAT32:
        return struct.pack("<f", value)
    if vtype == FLOAT64:
        return struct.pack("<d", value)
    return struct.pack("<?", bool(value))


def _sbom(path: Path) -> tuple[dict[str, str], dict[str, Any]]:
    """The model's ``ai_hyperparameter`` map and its annotation statement."""
    graph = json.loads(generate_model_sbom(path))["@graph"]
    package = next(e for e in graph if e.get("type") == "ai_AIPackage")
    hyper = {e["key"]: e["value"] for e in package.get("ai_hyperparameter", [])}
    statement = next(
        json.loads(e["statement"])
        for e in graph
        if e.get("type") == "Annotation" and '"artifact-metadata"' in e["statement"]
    )
    return hyper, statement


@pytest.mark.parametrize(
    ("vtype", "stored", "text", "kind"),
    [
        (FLOAT32, 1e-6, "0.000001", "float"),
        (FLOAT32, 1e-12, "1e-12", "float"),
        (FLOAT32, 9.999999747378752e-06, "0.00001", "float"),
        (FLOAT32, 0.1, "0.1", "float"),
        (FLOAT32, 10000.0, "10000", "float"),
        (FLOAT32, -0.0, "0", "float"),
        (FLOAT32, float("nan"), "NaN", "float"),
        (FLOAT32, float("-inf"), "-INF", "float"),
        (FLOAT64, 9.999999747378752e-06, "0.000009999999747378752", "float"),
        (FLOAT64, 1e-7, "1e-7", "float"),
        (BOOL, 1, "true", "boolean"),
        (BOOL, 0, "false", "boolean"),
    ],
    ids=[
        "f32-1e-6",
        "f32-1e-12",
        "f32-1e-5-widened",
        "f32-0.1",
        "f32-integral",
        "f32-negative-zero",
        "f32-nan",
        "f32-negative-inf",
        "f64-not-narrowed",
        "f64-exponent",
        "bool-true",
        "bool-false",
    ],
)
@pytest.mark.parametrize("key", ["x.value", _HYPER_KEY], ids=["property", "hyper"])
def test_gguf_scalar_has_one_spelling_in_every_sink(
    key: str, vtype: int, stored: float, text: str, kind: str, tmp_path: Path
) -> None:
    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, 1, kv(key.encode(), vtype, _value(vtype, stored))))
    meta = read_ai_model(path)
    hyper, statement = _sbom(path)
    if key == _HYPER_KEY:
        assert key not in meta.properties
        assert hyper[key] == text
    else:
        assert meta.properties[key] == text
        assert key not in hyper
    assert statement["metadata"][key] == text
    assert statement["valueTypes"][key] == kind
    if vtype == FLOAT32 and text not in ("NaN", "-INF"):
        # The narrowed double is the same float32 as stored.
        numpy = pytest.importorskip("numpy")
        assert numpy.float32(float(text)) == numpy.float32(stored)


@pytest.mark.parametrize(
    ("stored", "text"),
    [(1.0000001, "1.0000001"), (16777216.0, "16777216")],
    ids=["near-one", "two-to-24"],
)
@pytest.mark.parametrize(
    "options", [{"legacy": "1.13"}, {"precision": 2}], ids=["legacy", "precision"]
)
def test_float32_spelling_ignores_numpy_print_options(
    options: dict[str, Any], stored: float, text: str, tmp_path: Path
) -> None:
    numpy = pytest.importorskip("numpy")
    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, 1, kv(b"x.value", FLOAT32, _value(FLOAT32, stored))))
    with numpy.printoptions(**options):
        meta = read_ai_model(path)
    assert meta.properties["x.value"] == meta.raw_metadata["x.value"] == text


@pytest.mark.parametrize(
    ("key", "vtype", "stored", "text", "attr"),
    [
        ("general.name", BOOL, 1, "true", "name"),
        ("general.description", FLOAT32, 1e-6, "0.000001", "description"),
        ("general.version", FLOAT64, 1e-7, "1e-7", "version"),
        ("general.architecture", BOOL, 0, "false", "architecture"),
    ],
    ids=["name-bool", "description-f32", "version-f64", "architecture-bool"],
)
def test_a_core_field_is_spelt_as_its_property(
    key: str, vtype: int, stored: float, text: str, attr: str, tmp_path: Path
) -> None:
    """A non-string ``general.*`` value is the same text in the package
    field as in ``properties`` and the annotation."""
    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, 1, kv(key.encode(), vtype, _value(vtype, stored))))
    meta = read_ai_model(path)
    assert getattr(meta, attr) == meta.properties[key] == text
    assert meta.raw_metadata[key] == text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Apache-2.0", "Apache-2.0"),
        ("  MIT OR Apache-2.0\n", "MIT OR Apache-2.0"),
        ("", None),
        ("   ", None),
    ],
    ids=["id", "expression-trimmed", "empty", "blank"],
)
def test_general_license_is_the_model_licence(
    tmp_path: Path, value: str, expected: str | None
) -> None:
    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, 1, kv(b"general.license", STRING, string(value))))
    meta = read_ai_model(path)
    assert meta.license == expected
    # the key stays a property and in the verbatim metadata either way
    assert meta.properties["general.license"] == value
    if expected is None:
        assert "license" not in meta.provenance
    else:
        assert meta.provenance["license"].endswith("Field: general.license")
