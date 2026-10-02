# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""GGUF array fields: recorded as ``<key>.length`` (properties) and
``{"length", "type"}`` (raw metadata), never as an element.

See also: :mod:`tests.extract.ai_model.test_gguf` (the scalar fields) and
:mod:`tests.extract.ai_model.gguf_builders`.
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import json
import struct
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest

from pitloom.assemble import generate_model_sbom, generate_project_sbom
from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.extract.ai_model import gguf as gguf_reader
from pitloom.extract.ai_model.gguf import read_gguf
from pitloom.extract.ai_model.limits import MAX_MODEL_ENTRIES, cap_and_warn
from tests.extract.ai_model.gguf_builders import (
    ARRAY,
    INT32,
    STRING,
    UINT8,
    UINT32,
    array,
    gguf_file,
    kv,
    string,
)
from tests.warning_helpers import logged_warnings

_FIXTURES = sorted(
    (Path(__file__).parents[2] / "fixtures" / "aimodels" / "gguf").glob("*.gguf")
)
# The reader's own pseudo-fields (GGUF.version, .tensor_count, .kv_count).
_PSEUDO_FIELDS = 3


def _read(tmp_path: Path, n_kv: int, body: bytes) -> AiModelMetadata:
    pytest.importorskip("gguf")
    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, n_kv, body))
    return read_gguf(path)


def _provenance(key: str, source: str = "m.gguf") -> str:
    return f"Source: {source} | Field: {key} | Method: array_length"


@pytest.mark.parametrize("fixture", _FIXTURES, ids=lambda p: p.name)
def test_every_array_of_a_real_file_is_its_length(fixture: Path) -> None:
    """The oracle is the gguf library's own element list (none of the
    fixtures nests arrays, so it equals the declared count)."""
    gguf = pytest.importorskip("gguf")
    arrays = {
        key: (len(f.data), f.types[1].name)
        for key, f in gguf.GGUFReader(str(fixture)).fields.items()
        if f.types[0] == gguf.GGUFValueType.ARRAY
    }
    assert arrays  # non-vacuous: every fixture has a vocabulary or tags
    meta = read_gguf(fixture)
    for key, (length, element) in arrays.items():
        assert key not in meta.properties
        assert key not in meta.hyperparameters
        assert meta.properties[f"{key}.length"] == str(length)
        assert meta.raw_metadata[key] == {"length": length, "type": element}
        assert meta.provenance[f"properties.{key}.length"] == _provenance(
            key, fixture.name
        )


def test_the_stories_vocabulary_is_512_tokens_not_its_last_token() -> None:
    pytest.importorskip("gguf")
    meta = read_gguf(next(p for p in _FIXTURES if p.name == "stories260K.gguf"))
    assert meta.properties["tokenizer.ggml.tokens.length"] == "512"
    assert meta.properties["tokenizer.ggml.scores.length"] == "512"


_NESTED = struct.pack("<IQ", ARRAY, 2) + b"".join(
    struct.pack("<IQ", INT32, len(row)) + struct.pack(f"<{len(row)}i", *row)
    for row in ([1, 2], [3, 4, 5])
)


@pytest.mark.parametrize(
    ("key", "body", "raw"),
    [
        ("e", array(STRING, 0, key=b"e"), {"length": 0, "type": "STRING"}),
        ("u", array(99, 0, key=b"u"), {"length": 0}),  # not a GGUF type
        ("n", kv(b"n", ARRAY, _NESTED), {"length": 2, "type": "ARRAY"}),
        (
            "s",
            array(STRING, 2, string("a") + string("bc"), key=b"s"),
            {"length": 2, "type": "STRING"},
        ),
        (
            "llama.attention.head_count",
            array(
                INT32, 3, struct.pack("<3i", 4, 4, 8), key=b"llama.attention.head_count"
            ),
            {"length": 3, "type": "INT32"},
        ),
        (
            "general.name",
            array(STRING, 1, string("x"), key=b"general.name"),
            {"length": 1, "type": "STRING"},
        ),
    ],
    ids=["empty", "unknown-type", "nested", "strings", "hyperparameter-suffix", "name"],
)
def test_an_array_of_any_shape_is_its_top_level_length(
    key: str, body: bytes, raw: dict[str, Any], tmp_path: Path
) -> None:
    """An empty array is a length of 0, not absent, with the element type
    its header declares; a nested one counts its rows, not its leaves; a
    per-layer hyperparameter is a property; an array is never a name."""
    meta = _read(tmp_path, 1, body)
    assert meta.properties[f"{key}.length"] == str(raw["length"])
    assert meta.raw_metadata[key] == raw
    assert key not in meta.properties
    assert not meta.hyperparameters
    assert meta.name is None
    assert meta.provenance[f"properties.{key}.length"] == _provenance(key)


def test_an_array_length_is_never_a_hyperparameter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even under a suffix list that would match ``.length``."""
    monkeypatch.setattr(gguf_reader, "_GGUF_HYPERPARAM_SUFFIXES", (".length",))
    meta = _read(tmp_path, 1, array(UINT8, 1, b"\0", key=b"a"))
    assert meta.properties["a.length"] == "1"
    assert not meta.hyperparameters


_COLLIDING = (
    array(UINT8, 2, b"\0\0", key=b"x"),
    kv(b"x.length", UINT32, struct.pack("<I", 99)),
)


def test_an_array_beside_an_array_named_its_length_keeps_both(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Only a real scalar ``x.length`` wins; an array ``x.length`` is
    ``x.length.length`` and leaves ``x.length`` free."""
    body = array(UINT8, 1, b"\0", key=b"x") + array(UINT8, 2, b"\0\0", key=b"x.length")
    meta = _read(tmp_path, 2, body)
    assert meta.properties["x.length"] == "1"
    assert meta.properties["x.length.length"] == "2"
    assert not logged_warnings(caplog)


def test_hostile_array_key_text_is_escaped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A ``|`` cannot forge a provenance segment; a control character
    cannot reach the terminal."""
    key = b"a|Method: forged\x1b"
    body = array(UINT8, 1, b"\0", key=key) + kv(
        key + b".length", UINT32, struct.pack("<I", 7)
    )
    meta = _read(tmp_path, 3, body + array(UINT8, 1, b"\0", key=b"b|c"))
    assert meta.provenance["properties.b|c.length"] == _provenance("b/c")
    (message,) = logged_warnings(caplog)
    assert "\x1b" not in message
    assert "\\x1b" in message


@pytest.mark.parametrize("order", [1, -1], ids=["array-first", "key-first"])
def test_a_real_length_key_wins_over_an_array_length(
    order: int, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    body = b"".join(_COLLIDING[::order])
    assert body != b"".join(_COLLIDING[::-order])  # the two orders differ
    meta = _read(tmp_path, 2, body)
    assert meta.properties["x.length"] == "99"
    assert meta.provenance["properties.x.length"] == (
        "Source: m.gguf | Field: x.length"
    )
    assert meta.raw_metadata["x"] == {"length": 2, "type": "UINT8"}
    assert meta.raw_metadata["x.length"] == 99
    (message,) = logged_warnings(caplog)
    assert message == (
        "GGUF key x.length is in the file; the length of array x is not a property"
    )


def _cap_file(n_scalars: int) -> bytes:
    """An array first, then *n_scalars* scalars: file order differs from
    both key order and "arrays last"."""
    scalars = b"".join(
        kv(f"s{i:04d}".encode(), UINT32, struct.pack("<I", i)) for i in range(n_scalars)
    )
    return array(UINT8, 1, b"\0", key=b"z") + scalars


@pytest.mark.parametrize("over", [0, 1])
def test_an_array_length_is_one_entry_cut_in_file_order(
    over: int, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    n_scalars = MAX_MODEL_ENTRIES - _PSEUDO_FIELDS - 1 + over
    meta = _read(tmp_path, n_scalars + 1, _cap_file(n_scalars))
    order = list(meta.properties)
    assert len(order) == MAX_MODEL_ENTRIES + over
    cap_and_warn(meta, AiModelFormat.GGUF, "m.gguf")
    assert list(meta.properties) == order[:MAX_MODEL_ENTRIES]
    assert "z.length" in meta.properties
    assert "properties.z.length" in meta.provenance
    last = f"s{n_scalars - 1:04d}"
    assert (last in meta.properties) is not bool(over)
    assert (f"properties.{last}" in meta.provenance) is not bool(over)
    assert len(logged_warnings(caplog)) == over


def test_an_array_without_a_count_is_a_read_failure(tmp_path: Path) -> None:
    """The ``ReaderField.parts`` layout is the gguf library's, not an API:
    a field without one is refused, not guessed at."""
    gguf = pytest.importorskip("gguf")
    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, 0))
    broken = SimpleNamespace(types=[gguf.GGUFValueType.ARRAY], parts=[0, 0, 0, 0])
    reader = SimpleNamespace(fields={"k": broken})
    with mock.patch.object(gguf, "GGUFReader", return_value=reader):
        with pytest.raises(ValueError, match="Failed to read GGUF file .*count"):
            read_gguf(path)


def _model_view(sbom: str) -> tuple[str, dict[str, Any]]:
    """The AI package's comment and its artifact-metadata statement."""
    graph = json.loads(sbom)["@graph"]
    (package,) = [e for e in graph if e.get("type") == "ai_AIPackage"]
    (statement,) = [
        json.loads(e["statement"])
        for e in graph
        if e.get("type") == "Annotation"
        and "artifact-metadata" in e.get("statement", "")
    ]
    return str(package["comment"]), statement


def test_loom_model_and_a_project_scan_record_the_same_lengths(tmp_path: Path) -> None:
    pytest.importorskip("gguf")
    fixture = next(p for p in _FIXTURES if p.name == "stories260K.gguf")
    project = tmp_path / "proj"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (project / "demo" / fixture.name).write_bytes(fixture.read_bytes())
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n\n'
        '[tool.pitloom.provenance]\npreserve-source-metadata = "always"\n',
        encoding="utf-8",
    )
    scanned = generate_project_sbom(project, offline=True)
    single = generate_model_sbom(project / "demo" / fixture.name)
    for sbom in (scanned, single):
        assert "[226, 128, 138]" not in sbom
    assert _model_view(scanned) == _model_view(single)
    comment, statement = _model_view(single)
    assert _provenance("tokenizer.ggml.tokens", fixture.name) in comment
    assert statement["metadata"]["tokenizer.ggml.tokens"] == {
        "length": 512,
        "type": "STRING",
    }
