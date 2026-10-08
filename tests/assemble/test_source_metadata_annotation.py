# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The artifact-metadata annotation of every AI model format: a collection
is a JSON array (or object), a scalar is text, the same text as in
``properties`` and ``ai_hyperparameter``, spelt by
:func:`~pitloom.core.scalar_text.scalar_text` and typed in ``valueTypes``;
the keys are the reader's own.

See also: :func:`pitloom.core.ai_metadata.source_metadata` (the one rule
every reader applies) and :mod:`tests.core.test_ai_metadata` (its unit
tests).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import math
import pickle  # nosec B403 -- writes a test file, never loads one
import re
import struct
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from pitloom.assemble import generate_model_sbom
from pitloom.core.ai_metadata import SOURCE_METADATA_MAX_DEPTH, AiModelFormat
from pitloom.core.canonical_json import canonical_json
from pitloom.core.scalar_text import scalar_text
from pitloom.extract.ai_model import read_ai_model
from tests.extract.ai_model.gguf_builders import (
    BOOL,
    FLOAT32,
    FLOAT64,
    UINT64,
    gguf_file,
    kv,
)

_AIMODELS = Path(__file__).parents[1] / "fixtures" / "aimodels"

# Fixture folder -> format. The hdf5/ fixture carries keras_version, so it
# reads as Keras; a plain HDF5 model is a crafted case below.
_FOLDER_FORMATS = {
    "crfsuite": AiModelFormat.CRFSUITE,
    "fasttext": AiModelFormat.FASTTEXT,
    "gguf": AiModelFormat.GGUF,
    "hdf5": AiModelFormat.KERAS,
    "keras": AiModelFormat.KERAS,
    "numpy": AiModelFormat.NUMPY,
    "onnx": AiModelFormat.ONNX,
    "pytorch": AiModelFormat.PYTORCH,
    "pytorch_pt2": AiModelFormat.PYTORCH_PT2,
    "safetensors": AiModelFormat.SAFETENSORS,
}

# Library each format's reader needs.
_LIBRARIES = {
    AiModelFormat.FASTTEXT: "fasttext",
    AiModelFormat.GGUF: "gguf",
    AiModelFormat.HDF5: "h5py",
    AiModelFormat.NUMPY: "numpy",
    AiModelFormat.ONNX: "onnx",
    AiModelFormat.SAFETENSORS: "safetensors",
}

# Keys whose value is a collection in the file, per fixture folder.
_FOLDER_LISTS = {
    "crfsuite": {"labels"},
    "fasttext": {"labels"},
    "pytorch": {"archive_contents"},
    "pytorch_pt2": {"archive_contents", "tags"},
}

_TRAINING_CONFIG = {
    "loss": "mse",
    "optimizer_config": {"class_name": "Adam", "config": {}},
}


class _Case(NamedTuple):
    fmt: AiModelFormat
    make: Callable[[Path], Path]
    lists: frozenset[str] = frozenset()
    expected: dict[str, Any] | None = None


def _fixture(path: Path) -> _Case:
    return _Case(
        _FOLDER_FORMATS[path.parent.name],
        lambda _tmp: path,
        frozenset(_FOLDER_LISTS.get(path.parent.name, ())),
    )


def _h5(attrs: dict[str, str]) -> Callable[[Path], Path]:
    def make(tmp_path: Path) -> Path:
        h5py = pytest.importorskip("h5py")
        path = tmp_path / "m.h5"
        with h5py.File(path, "w") as hf:
            for key, value in attrs.items():
                hf.attrs[key] = value
        return path

    return make


def _gguf(tmp_path: Path) -> Path:
    path = tmp_path / "m.gguf"
    body = (
        kv(b"big", UINT64, struct.pack("<Q", 2**63 + 1))
        + kv(b"flag", BOOL, b"\x01")
        + kv(b"eps", FLOAT32, struct.pack("<f", 1e-6))
        + kv(b"wide", FLOAT64, struct.pack("<d", 1e-6 + 2**-60))
        + kv(b"nan", FLOAT32, struct.pack("<f", float("nan")))
    )
    path.write_bytes(gguf_file(0, 5, body))
    return path


# Over the 20 names the listing shows.
_MEMBERS = [f"archive/data/{i}" for i in range(25)]
_TAGS = ["x", True, None, 1, 0.5]


def _zip(suffix: str, names: list[str]) -> Callable[[Path], Path]:
    contents = {"version": b"2\n", "extra/tags": json.dumps(_TAGS).encode()}

    def make(tmp_path: Path) -> Path:
        path = tmp_path / f"m{suffix}"
        with zipfile.ZipFile(path, "w") as zf:
            for name in names:
                zf.writestr(name, contents.get(name, b""))
        return path

    return make


def _raw_pickle(tmp_path: Path) -> Path:
    path = tmp_path / "m.pt"
    path.write_bytes(pickle.dumps({"weight": [1.0]}))
    return path


_CRAFTED = {
    "hdf5-metrics-list": _Case(
        AiModelFormat.HDF5,
        _h5(
            {
                "backend": "tensorflow",
                "training_config": json.dumps(
                    {**_TRAINING_CONFIG, "metrics": ["mae", "accuracy"]}
                ),
            }
        ),
        frozenset({"metrics"}),
        {"metrics": ["mae", "accuracy"], "loss": "mse"},
    ),
    "keras-metrics-object": _Case(
        AiModelFormat.KERAS,
        _h5(
            {
                "keras_version": "2.15.0",
                "training_config": json.dumps(
                    {**_TRAINING_CONFIG, "metrics": {"out": ["acc", 1]}}
                ),
            }
        ),
        frozenset({"metrics"}),
        {"metrics": {"out": ["acc", "1"]}},
    ),
    "hdf5-metrics-json-scalars": _Case(
        AiModelFormat.HDF5,
        _h5(
            {
                "backend": "tensorflow",
                "training_config": json.dumps(
                    {**_TRAINING_CONFIG, "metrics": {"acc": True, "f": None}}
                ),
            }
        ),
        frozenset({"metrics"}),
        {"metrics": {"acc": "true", "f": "null"}},
    ),
    "pytorch-25-members": _Case(
        AiModelFormat.PYTORCH,
        _zip(".pt", _MEMBERS),
        frozenset({"archive_contents"}),
        {"archive_contents": _MEMBERS[:20], "archive_member_count": "25"},
    ),
    "pt2-25-members-tags": _Case(
        AiModelFormat.PYTORCH_PT2,
        _zip(".pt2", ["version", "extra/tags", *_MEMBERS[2:]]),
        frozenset({"archive_contents", "tags"}),
        {
            "archive_contents": ["version", "extra/tags", *_MEMBERS[2:20]],
            "archive_member_count": "25",
            "tags": ["x", "true", "null", "1", "0.5"],
        },
    ),
    "gguf-wide-scalars": _Case(
        AiModelFormat.GGUF,
        _gguf,
        expected={
            "big": "9223372036854775809",
            "flag": "true",
            "eps": "0.000001",
            "wide": "0.0000010000000000008673",
            "nan": "NaN",
        },
    ),
    "pytorch-raw-pickle": _Case(
        AiModelFormat.PYTORCH,
        _raw_pickle,
        expected={"format_detail": "raw pickle"},
    ),
}

_FIXTURES = sorted(
    p
    for folder in _FOLDER_FORMATS
    for p in (_AIMODELS / folder).iterdir()
    if p.is_file() and p.suffix not in {".md", ".py"} and p.name != ".gitkeep"
)
_CASES = {f"{p.parent.name}/{p.name}": _fixture(p) for p in _FIXTURES} | _CRAFTED


class _Sbom(NamedTuple):
    statement: dict[str, Any] | None  # the artifact-metadata statement
    hyperparameters: dict[str, str]  # ai_hyperparameter, key -> value


def _sbom(path: Path) -> _Sbom:
    graph = json.loads(generate_model_sbom(path))["@graph"]
    statements = [
        json.loads(e["statement"])
        for e in graph
        if e.get("type") == "Annotation"
        and '"artifact-metadata"' in e.get("statement", "")
    ]
    assert len(statements) <= 1
    package = next(e for e in graph if e.get("type") == "ai_AIPackage")
    hyper = {e["key"]: e["value"] for e in package.get("ai_hyperparameter", [])}
    return _Sbom(statements[0] if statements else None, hyper)


def _annotation_metadata(path: Path) -> dict[str, Any] | None:
    statement = _sbom(path).statement
    return statement["metadata"] if statement else None


def _scalars(value: Any) -> list[Any]:
    """Every non-collection value in *value*, at any depth."""
    if isinstance(value, dict):
        return [s for item in value.values() for s in _scalars(item)]
    if isinstance(value, list):
        return [s for item in value for s in _scalars(item)]
    return [value]


def _json_collection(text: str) -> list[Any] | dict[str, Any] | None:
    """*text* parsed, when it is the JSON text of a list or an object."""
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, (list, dict)) else None


def _spelt(value: Any) -> Any:
    """*value* with each scalar spelt as in its JSON text."""
    if isinstance(value, dict):
        return {key: _spelt(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_spelt(item) for item in value]
    return value if isinstance(value, str) else json.dumps(value)


def _file_keys(path: Path, fmt: AiModelFormat) -> dict[str, str] | None:
    """The keys the file itself names, when they are not its properties,
    each with the type the file declares (``ARRAY``, ``FLOAT32``, ...)."""
    if fmt is not AiModelFormat.GGUF:
        return None
    gguf = pytest.importorskip("gguf")
    return {
        key: field.types[0].name if field.types else ""
        for key, field in gguf.GGUFReader(str(path)).fields.items()
    }


# Properties a reader holds as the text of an integer (every other key of a
# format with no file-declared types is a string or a collection).
_INTEGER_PROPERTIES = frozenset(
    {
        "archive_member_count",
        "layer_count",
        "num_attributes",
        "num_features",
        "num_labels",
    }
)


def _expected_type(key: str, file_type: str | None) -> str | None:
    """The ``valueTypes`` entry *key* must have, from the GGUF type the file
    declares, else from its property name."""
    if file_type is not None:
        if file_type == "BOOL":
            return "boolean"
        if file_type.startswith(("INT", "UINT")):
            return "integer"
        return "float" if file_type.startswith("FLOAT") else None
    if key in _INTEGER_PROPERTIES or key.startswith("opset."):
        return "integer"
    return None


_TYPE_PATTERNS = {
    "integer": re.compile(r"-?\d+"),
    "boolean": re.compile(r"true|false"),
}

# Python's and JSON's own spellings, which scalar_text never writes.
_FOREIGN_SPELLINGS = frozenset(
    {"True", "False", "inf", "-inf", "nan", "Infinity", "-Infinity"}
)


def _check_value_types(
    statement: dict[str, Any], file_keys: dict[str, str] | None
) -> None:
    """``valueTypes`` names exactly the non-string scalar keys, each typed as
    its text is spelt; it is absent when empty."""
    metadata = statement["metadata"]
    types = statement.get("valueTypes")
    assert types != {}  # left out when empty
    expected = {
        key: kind
        for key in metadata
        if isinstance(metadata[key], str)
        and (kind := _expected_type(key, (file_keys or {}).get(key)))
    }
    assert (types or {}) == expected
    for key, kind in expected.items():
        text = metadata[key]
        if kind == "float":
            number = float(text)
            assert scalar_text(number) == text
            assert math.isfinite(number) or text in {"NaN", "INF", "-INF"}
        else:
            assert _TYPE_PATTERNS[kind].fullmatch(text), (key, text)


@pytest.mark.parametrize("case_id", sorted(_CASES))
def test_annotation_collections_are_arrays_and_scalars_text(
    case_id: str, tmp_path: Path
) -> None:
    case = _CASES[case_id]
    if case.fmt in _LIBRARIES:
        pytest.importorskip(_LIBRARIES[case.fmt])
    path = case.make(tmp_path)
    meta = read_ai_model(path)
    assert meta.format_info.model_format is case.fmt
    sbom = _sbom(path)
    metadata = sbom.statement["metadata"] if sbom.statement else None

    file_keys = _file_keys(path, case.fmt)
    expected_keys = file_keys if file_keys is not None else list(meta.properties)
    # The serialised statement sorts its keys, so the order is not compared.
    assert sorted(metadata or {}) == sorted(expected_keys)
    for key, native in meta.hyperparameters.items():
        assert sbom.hyperparameters[key] == scalar_text(native)
    texts = [*meta.properties.values(), *sbom.hyperparameters.values()]
    assert _FOREIGN_SPELLINGS.isdisjoint(texts + _scalars(metadata or {}))
    if sbom.statement is None or metadata is None:
        return
    _check_value_types(sbom.statement, file_keys)
    for scalar in _scalars(metadata):
        assert isinstance(scalar, str), (scalar, type(scalar))
        assert _json_collection(scalar) is None, scalar
    assert {k for k, v in metadata.items() if isinstance(v, (list, dict))} == (
        set(case.lists)
        | {k for k in metadata if file_keys and f"{k}.length" in meta.properties}
    )
    for key, value in metadata.items():
        text = meta.properties.get(key)
        if isinstance(value, str):
            assert text is None or value == text
        elif text is not None and (parsed := _json_collection(text)) is not None:
            assert value == _spelt(parsed)  # elements spelt as in the text
        if key in sbom.hyperparameters:
            assert value == sbom.hyperparameters[key]
    for key, value in (case.expected or {}).items():
        assert metadata[key] == value


def _embedded_json(value: Any) -> list[str]:
    """Every string at any depth of *value* that is the JSON text of a list
    or an object, and every such string inside those, at any depth."""
    if isinstance(value, dict):
        return [t for item in value.values() for t in _embedded_json(item)]
    if isinstance(value, list):
        return [t for item in value for t in _embedded_json(item)]
    if isinstance(value, str) and (parsed := _json_collection(value)) is not None:
        return [value, *_embedded_json(parsed)]
    return []


@pytest.mark.parametrize("case_id", sorted(_CASES))
def test_every_embedded_json_text_is_canonical(case_id: str, tmp_path: Path) -> None:
    """Each JSON text in an SBOM string (an annotation statement,
    ``ai_informationAboutApplication``) is RFC 8785, and so is each one
    inside it."""
    case = _CASES[case_id]
    if case.fmt in _LIBRARIES:
        pytest.importorskip(_LIBRARIES[case.fmt])
    texts = _embedded_json(json.loads(generate_model_sbom(case.make(tmp_path))))
    assert texts  # the statements at least
    for text in texts:
        assert text == canonical_json(json.loads(text)), text


def test_every_model_format_has_a_case() -> None:
    covered = {case.fmt for case in _CASES.values()}
    assert covered == set(AiModelFormat) - {AiModelFormat.UNKNOWN}
    model_folders = {
        p.parent.name
        for p in _AIMODELS.glob("*/*")
        if p.is_file() and p.suffix not in {".md", ".py"} and p.name != ".gitkeep"
    }
    assert model_folders - {"hostile"} == set(_FOLDER_FORMATS)


@pytest.mark.parametrize("depth", [500, 800], ids=["500", "800"])
def test_hostile_metrics_nesting_keeps_the_model(depth: int, tmp_path: Path) -> None:
    """A nesting the stack cannot walk (any over about 490 levels) is cut
    to text at the bound; the reader keeps every other field."""
    metrics = "[" * depth + '"acc"' + "]" * depth
    config = json.dumps(_TRAINING_CONFIG)[:-1] + f', "metrics": {metrics}}}'
    path = _h5({"backend": "tensorflow", "training_config": config})(tmp_path)
    assert read_ai_model(path).properties["loss"] == "mse"
    value = (_annotation_metadata(path) or {})["metrics"]
    for _ in range(SOURCE_METADATA_MAX_DEPTH):
        assert isinstance(value, list)
        value = value[0]
    assert isinstance(value, str)
