# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The artifact-metadata annotation of every AI model format: a collection
is a JSON array (or object), a scalar is text, the same text as in
``properties``; the keys are the reader's own.

See also: :func:`pitloom.core.ai_metadata.source_metadata` (the one rule
every reader applies) and :mod:`tests.core.test_ai_metadata` (its unit
tests).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import pickle  # nosec B403 -- writes a test file, never loads one
import struct
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from pitloom.assemble import generate_model_sbom
from pitloom.core.ai_metadata import SOURCE_METADATA_MAX_DEPTH, AiModelFormat
from pitloom.extract.ai_model import read_ai_model
from tests.extract.ai_model.gguf_builders import FLOAT32, gguf_file, kv

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

_BOOL, _UINT64 = 7, 10
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
        kv(b"big", _UINT64, struct.pack("<Q", 2**63 + 1))
        + kv(b"flag", _BOOL, b"\x01")
        + kv(b"eps", FLOAT32, struct.pack("<f", 1e-6))
    )
    path.write_bytes(gguf_file(0, 3, body))
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
        expected={"big": "9223372036854775809", "flag": "True"},
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


def _annotation_metadata(path: Path) -> dict[str, Any] | None:
    graph = json.loads(generate_model_sbom(path))["@graph"]
    statements = [
        json.loads(e["statement"])
        for e in graph
        if e.get("type") == "Annotation"
        and '"artifact-metadata"' in e.get("statement", "")
    ]
    assert len(statements) <= 1
    return statements[0]["metadata"] if statements else None


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


def _file_keys(path: Path, fmt: AiModelFormat) -> list[str] | None:
    """The keys the file itself names, when they are not its properties."""
    if fmt is not AiModelFormat.GGUF:
        return None
    gguf = pytest.importorskip("gguf")
    return list(gguf.GGUFReader(str(path)).fields)


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
    metadata = _annotation_metadata(path)

    file_keys = _file_keys(path, case.fmt)
    expected_keys = file_keys if file_keys is not None else list(meta.properties)
    # The serialised statement sorts its keys, so the order is not compared.
    assert sorted(metadata or {}) == sorted(expected_keys)
    if metadata is None:
        return
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
        if key in meta.hyperparameters:
            assert value == str(meta.hyperparameters[key])
    for key, value in (case.expected or {}).items():
        assert metadata[key] == value


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
