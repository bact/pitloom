# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Safetensors parameter count (the sum of every tensor's elements, from
the header's shapes alone) and the one originator of ``modelspec.author``.

See also: :mod:`tests.extract.ai_model.test_safetensors`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pitloom.assemble import generate_model_sbom
from pitloom.core.ai_metadata import MAX_MODEL_ENTRIES, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.model_originators import ORIGINATORS_PROVENANCE_KEY
from pitloom.core.model_parameters import PARAMETER_COUNT_PROVENANCE_KEY
from pitloom.extract.ai_model.limits import cap_entries
from pitloom.extract.ai_model.safetensors import read_safetensors

_ST = Path(__file__).parent.parent.parent / "fixtures" / "aimodels" / "safetensors"
_KEY = PARAMETER_COUNT_PROVENANCE_KEY
_PROVENANCE = (
    "Source: {} | Field: tensor shapes (header only) | Method: tensor_element_sum"
)


def _file(
    path: Path, shapes: dict[str, list[int]], metadata: dict[str, str] | None = None
) -> Path:
    """A valid Safetensors file of one-byte (``U8``) tensors of *shapes*, with
    *metadata* as its ``__metadata__``."""
    table: dict[str, object] = {"__metadata__": metadata} if metadata else {}
    offset = 0
    for name, shape in shapes.items():
        size = 1
        for dim in shape:
            size *= dim
        table[name] = {
            "dtype": "U8",
            "shape": shape,
            "data_offsets": [offset, offset + size],
        }
        offset += size
    header = json.dumps(table).encode()
    path.write_bytes(struct.pack("<Q", len(header)) + header + b"\0" * offset)
    return path


def _mocked(shapes: list[object]) -> MagicMock:
    """A ``safetensors`` module whose one file has a tensor of each of *shapes*."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.metadata.return_value = {}
    ctx.keys.return_value = [f"t{i}" for i in range(len(shapes))]
    ctx.get_slice.return_value.get_shape.side_effect = shapes
    module = MagicMock()
    module.safe_open.return_value = ctx
    return module


@pytest.mark.parametrize(
    ("name", "count"),
    [
        ("marian-tiny-random", 174535),
        ("phi-tiny-random", 80074),
        ("speech2text-tiny-random", 173968),
        ("vits-tiny-random", 74142),
        ("whisper-tiny-random", 216632),
    ],
)
def test_a_fixture_count_is_the_sum_of_its_tensor_elements(
    name: str, count: int
) -> None:
    pytest.importorskip("safetensors")
    meta = read_safetensors(_ST / f"{name}.safetensors")
    assert meta.parameter_count == count
    assert meta.provenance[_KEY] == _PROVENANCE.format(f"{name}.safetensors")


@pytest.mark.parametrize(
    "shapes",
    [{}, {"a": [0], "b": [3, 0, 2]}],
    ids=["empty-header", "zero-size"],
)
def test_no_element_means_no_count_and_no_provenance(
    tmp_path: Path, shapes: dict[str, list[int]]
) -> None:
    pytest.importorskip("safetensors")
    meta = read_safetensors(_file(tmp_path / "m.safetensors", shapes))
    assert meta.parameter_count is None
    assert _KEY not in meta.provenance


def test_a_scalar_tensor_counts_one_and_the_rest_add_up(tmp_path: Path) -> None:
    pytest.importorskip("safetensors")
    model = _file(tmp_path / "m.safetensors", {"s": [], "v": [4], "m": [2, 3]})
    assert read_safetensors(model).parameter_count == 1 + 4 + 6


@pytest.mark.parametrize(
    ("shape", "text"),
    [([10**8, 10**8], "parameter-count cap"), (["a"], "not a non-negative integer")],
    ids=["over-cap", "not-int"],
)
def test_a_rejected_shape_gives_one_warning_and_no_count(
    shape: object,
    text: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    model = tmp_path / "m.safetensors"
    model.write_bytes(b"fake")
    with patch.dict("sys.modules", {"safetensors": _mocked([[1], shape])}):
        with caplog.at_level(logging.WARNING):
            meta = read_safetensors(model)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "parameter count not recorded" in warnings[0].getMessage()
    assert text in warnings[0].getMessage()
    assert meta.parameter_count is None  # never a partial sum
    assert _KEY not in meta.provenance
    assert len(meta.inputs) == 2  # the rest of the read is unaffected


def test_a_shape_that_cannot_be_read_fails_the_read(tmp_path: Path) -> None:
    model = tmp_path / "m.safetensors"
    model.write_bytes(b"fake")
    module = _mocked([[1]])
    module.safe_open.return_value.get_slice.side_effect = RuntimeError("bad slice")
    with patch.dict("sys.modules", {"safetensors": module}):
        with pytest.raises(ValueError, match="Failed to read Safetensors"):
            read_safetensors(model)


def test_the_count_covers_every_tensor_not_only_the_entries_kept(
    tmp_path: Path,
) -> None:
    pytest.importorskip("safetensors")
    tensors = MAX_MODEL_ENTRIES + 1
    names = {f"t{i:04d}": [1] for i in range(tensors)}
    model = _file(tmp_path / "m.safetensors", names)

    meta: AiModelMetadata = read_safetensors(model)
    assert cap_entries(meta) == ["inputs"]
    assert len(meta.inputs) == MAX_MODEL_ENTRIES  # cut, the count is not
    assert meta.parameter_count == tensors
    assert meta.provenance[_KEY] == _PROVENANCE.format("m.safetensors")

    sbom = generate_model_sbom(
        model,
        creation_metadata=CreationMetadata(creation_datetime="2026-01-01T00:00:00Z"),
        id_registry=None,
    )
    (package,) = [e for e in json.loads(sbom)["@graph"] if e["type"] == "ai_AIPackage"]
    entries = {e["key"]: e["value"] for e in package["ai_hyperparameter"]}
    assert entries["parameters"] == str(tensors)
    kept = json.loads(package["ai_informationAboutApplication"])["inputs"]
    assert len(kept) == MAX_MODEL_ENTRIES


_AUTHOR = "modelspec.author"
_AUTHOR_PROVENANCE = "Source: m.safetensors | Field: __metadata__.modelspec.author"


@pytest.mark.parametrize(
    ("metadata", "names"),
    [
        ({_AUTHOR: "Jane"}, ["Jane"]),
        ({_AUTHOR: "  Jane  "}, ["Jane"]),
        ({_AUTHOR: "Doe, Jane"}, ["Doe, Jane"]),  # one name, not split
        ({_AUTHOR: ""}, []),
        ({_AUTHOR: "   "}, []),
        ({"author": "Jane"}, []),  # not a ModelSpec key
        ({"modelspec.title": "t"}, []),
        (None, []),
    ],
    ids=["one", "stripped", "comma", "empty", "blank", "other-key", "absent", "no-map"],
)
def test_modelspec_author_is_one_originator(
    tmp_path: Path, metadata: dict[str, str] | None, names: list[str]
) -> None:
    pytest.importorskip("safetensors")
    meta = read_safetensors(_file(tmp_path / "m.safetensors", {"a": [1]}, metadata))
    assert meta.originators == names
    if names:
        assert meta.provenance[ORIGINATORS_PROVENANCE_KEY] == _AUTHOR_PROVENANCE
        assert meta.properties[_AUTHOR] == (metadata or {})[_AUTHOR]  # key kept
    else:
        assert ORIGINATORS_PROVENANCE_KEY not in meta.provenance


def test_modelspec_author_becomes_an_agent_in_the_sbom(tmp_path: Path) -> None:
    pytest.importorskip("safetensors")
    model = _file(tmp_path / "m.safetensors", {"a": [1]}, {_AUTHOR: "Doe, Jane"})
    sbom = generate_model_sbom(
        model,
        creation_metadata=CreationMetadata(creation_datetime="2026-01-01T00:00:00Z"),
        id_registry=None,
    )
    graph = json.loads(sbom)["@graph"]
    (agent,) = [e for e in graph if e["type"] == "Agent"]
    (package,) = [e for e in graph if e["type"] == "ai_AIPackage"]
    assert agent["name"] == "Doe, Jane"
    assert package["originatedBy"] == [agent["spdxId"]]
