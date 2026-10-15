# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""GGUF producer (``general.author``, ``general.organization``) and the
parameter count summed from the tensor infos (``tensor_infos``).

See also: :mod:`tests.extract.ai_model.test_gguf` (the other fields) and
:mod:`tests.extract.ai_model.gguf_builders` (the file builders).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import struct
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.model_originators import ORIGINATORS_PROVENANCE_KEY
from pitloom.core.model_parameters import PARAMETER_COUNT_PROVENANCE_KEY
from pitloom.extract.ai_model.gguf import read_gguf
from tests.extract.ai_model.gguf_builders import (
    BOOL,
    STRING,
    UINT32,
    gguf_file,
    gguf_with_tensors,
    kv,
    string,
    tensor_info,
)
from tests.warning_helpers import logged_warnings

_FIXTURES = Path(__file__).parents[2] / "fixtures" / "aimodels" / "gguf"
_COUNT_PROVENANCE = "Source: m.gguf | Field: tensor_infos | Method: tensor_element_sum"
_AUTHOR = "general.author"
_ORG = "general.organization"
# ``ggml_type`` of Q4_0: blocks of 32 elements in 18 bytes
_Q4_0 = 2


def _text(key: str, value: str) -> bytes:
    return kv(key.encode(), STRING, string(value))


def _number(key: str, value: int) -> bytes:
    return kv(key.encode(), UINT32, struct.pack("<I", value))


def _read(
    tmp_path: Path,
    pairs: tuple[bytes, ...] = (),
    tensors: tuple[bytes, ...] = (),
    data_bytes: int = 0,
) -> AiModelMetadata:
    pytest.importorskip("gguf")
    path = tmp_path / "m.gguf"
    path.write_bytes(
        gguf_with_tensors(list(tensors), len(pairs), b"".join(pairs), data_bytes)
    )
    return read_gguf(path)


@pytest.mark.parametrize(
    ("name", "count"),
    [
        ("stories260K.gguf", 292800),
        ("mmproj-tinygemma3.gguf", 844288),
        ("ggml-vocab-phi-3.gguf", None),
        ("ggml-vocab-bert-bge.gguf", None),
    ],
)
def test_the_fixtures_count(name: str, count: int | None) -> None:
    pytest.importorskip("gguf")
    meta = read_gguf(_FIXTURES / name)
    assert meta.parameter_count == count
    assert (PARAMETER_COUNT_PROVENANCE_KEY in meta.provenance) is (count is not None)
    assert not meta.originators


@pytest.mark.parametrize(
    ("tensors", "data_bytes", "count"),
    [
        ((tensor_info("a", (2, 3)), tensor_info("b", (4,))), 24, 10),
        ((tensor_info("a", ()),), 4, 1),
        ((tensor_info("a", (0, 5)),), 0, None),
        ((tensor_info("a", (32, 2), _Q4_0),), 36, 64),
        ((), 0, None),
    ],
    ids=["two", "scalar", "empty", "q4_0-elements", "none"],
)
def test_the_sum_of_the_tensor_elements(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    tensors: tuple[bytes, ...],
    data_bytes: int,
    count: int | None,
) -> None:
    meta = _read(tmp_path, tensors=tensors, data_bytes=data_bytes)
    assert meta.parameter_count == count
    assert meta.provenance.get(PARAMETER_COUNT_PROVENANCE_KEY) == (
        None if count is None else _COUNT_PROVENANCE
    )
    assert not logged_warnings(caplog)


def test_a_wrapping_shape_is_a_read_failure(tmp_path: Path) -> None:
    """The reader's own ``numpy.prod`` wraps to 0 and it refuses the file."""
    with pytest.raises(ValueError, match="Failed to read GGUF file"):
        _read(tmp_path, tensors=(tensor_info("a", (2**32, 2**32)),))


def test_a_count_over_the_cap_is_one_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pytest.importorskip("gguf")
    # pylint: disable-next=import-outside-toplevel
    import gguf

    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, 0))
    huge = SimpleNamespace(shape=SimpleNamespace(tolist=lambda: [10**8, 10**8]))
    reader = SimpleNamespace(fields={}, tensors=[huge])
    with mock.patch.object(gguf, "GGUFReader", return_value=reader):
        meta = read_gguf(path)
    assert meta.parameter_count is None
    assert PARAMETER_COUNT_PROVENANCE_KEY not in meta.provenance
    (warning,) = logged_warnings(caplog)
    assert "parameter-count cap" in warning
    assert "parameter count not recorded" in warning


@pytest.mark.parametrize(
    ("split", "count"),
    [
        (_number("split.count", 3), None),
        (_number("split.count", 2), None),
        (_number("split.count", 1), 6),
        (_number("split.count", 0), 6),
        (_text("split.count", "3"), 6),
        (kv(b"split.count", BOOL, b"\x01"), 6),
    ],
    ids=["three", "two", "one", "zero", "string", "bool"],
)
def test_a_split_file_has_no_count(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    split: bytes,
    count: int | None,
) -> None:
    """A shard holds part of the tensors: its sum would understate the model."""
    meta = _read(tmp_path, (split,), (tensor_info("a", (2, 3)),), data_bytes=24)
    assert meta.parameter_count == count
    assert (PARAMETER_COUNT_PROVENANCE_KEY in meta.provenance) is (count is not None)
    assert not logged_warnings(caplog)


_ORIGINATORS = [
    ((), [], None),
    ((_text(_AUTHOR, "  "),), [], None),
    ((_number(_AUTHOR, 5),), [], None),
    ((_text(_AUTHOR, " Jane "),), ["Jane"], _AUTHOR),
    ((_text(_ORG, "Acme"),), ["Acme"], _ORG),
    ((_number(_AUTHOR, 5), _text(_ORG, "Acme")), ["Acme"], _ORG),
    ((_text(_AUTHOR, ""), _text(_ORG, "Acme")), ["Acme"], _ORG),
    (
        (_text(_ORG, "Acme"), _text(_AUTHOR, "Jane")),
        ["Jane", "Acme"],
        f"{_AUTHOR}, {_ORG}",
    ),
    ((_text(_AUTHOR, "Acme"), _text(_ORG, "Acme")), ["Acme"], f"{_AUTHOR}, {_ORG}"),
    ((_text(_AUTHOR, "Doe, Jane"),), ["Doe, Jane"], _AUTHOR),
]


@pytest.mark.parametrize(
    ("pairs", "names", "field"),
    _ORIGINATORS,
    ids=[
        "absent",
        "blank",
        "uint32",
        "author",
        "organization",
        "uint32-author-and-org",
        "blank-author-and-org",
        "both-author-first",
        "same-twice",
        "comma-is-one-name",
    ],
)
def test_the_originators(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    pairs: tuple[bytes, ...],
    names: list[str],
    field: str | None,
) -> None:
    meta = _read(tmp_path, pairs)
    assert meta.originators == names
    assert meta.provenance.get(ORIGINATORS_PROVENANCE_KEY) == (
        None if field is None else f"Source: m.gguf | Field: {field}"
    )
    assert not logged_warnings(caplog)


def test_the_raw_keys_stay_properties(tmp_path: Path) -> None:
    meta = _read(tmp_path, (_text(_AUTHOR, "Jane"), _text(_ORG, "Acme")))
    assert meta.properties[_AUTHOR] == "Jane"
    assert meta.properties[_ORG] == "Acme"
    assert meta.provenance[f"properties.{_AUTHOR}"] == (
        f"Source: m.gguf | Field: {_AUTHOR}"
    )
