# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Edge-case tests for the PyTorch PT2 Archive metadata extractor.

See also: :mod:`tests.extract.ai_model.test_pytorch_pt2` for the primary mocked and
integration test suite.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import io as _io
import json as _json
import logging
import zipfile as _zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pitloom.extract.ai_model.pytorch_pt2 import (
    _read_pt2_format_version,
    _read_pt2_graph_io,
    _read_pt2_zip,
    read_pytorch_pt2,
)
from pitloom.extract.scanner import read_model_candidate
from pitloom.extract.scanner_project import local_model_candidate

from .test_pytorch_pt2 import _make_pt2_zip


def _tensor(name: object) -> dict[str, object]:
    return {"arg": {"as_tensor": {"name": name}}}


def _graph_io(
    input_specs: object, output_specs: object, *, signature: bool = True
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, str]]:
    """Read a ``model.json`` whose graph lists every placeholder."""
    module: dict[str, object] = {
        "graph": {
            "inputs": [{"as_tensor": {"name": n}} for n in ("p_w", "b_m", "x")],
            "outputs": [{"as_tensor": {"name": "y"}}],
        }
    }
    if signature:
        module["signature"] = {
            "input_specs": input_specs,
            "output_specs": output_specs,
        }
    buf = _make_pt2_zip(
        {"models/model.json": _json.dumps({"graph_module": module}).encode()}
    )
    provenance: dict[str, str] = {}
    with _zipfile.ZipFile(_io.BytesIO(buf)) as zf:
        inputs, outputs = _read_pt2_graph_io(zf, "", "Source: model.pt2", provenance)
    return inputs, outputs, provenance


def test_only_the_signature_s_user_inputs_and_outputs_count() -> None:
    """Parameters, buffers, constants and tokens are placeholders of the graph,
    not inputs; a buffer mutation or a loss is not an output."""
    inputs, outputs, provenance = _graph_io(
        [
            {"parameter": {**_tensor("p_w"), "parameter_name": "w"}},
            {"buffer": {**_tensor("b_m"), "buffer_name": "m"}},
            {"tensor_constant": {**_tensor("c_k"), "tensor_constant_name": "k"}},
            {"token": _tensor("tok")},
            {"user_input": _tensor("x")},
        ],
        [
            {"buffer_mutation": {**_tensor("b_m"), "buffer_name": "m"}},
            {"loss_output": _tensor("loss")},
            {"user_output": _tensor("y")},
        ],
    )
    assert (inputs, outputs) == ([{"name": "x"}], [{"name": "y"}])
    assert "user_input" in provenance["inputs"]
    assert "user_output" in provenance["outputs"]


def test_a_graph_without_a_signature_gives_no_inputs_or_outputs() -> None:
    """The graph alone cannot tell a weight from an input: nothing is guessed."""
    inputs, outputs, provenance = _graph_io(None, None, signature=False)
    assert (inputs, outputs, provenance) == ([], [], {})


@pytest.mark.parametrize(
    "specs",
    [
        None,
        "x",
        {"user_input": _tensor("x")},  # a mapping, not a list
        ["not-a-dict", 3, None],
        [{"user_input": "x"}, {"user_input": {"arg": "x"}}],
        [{"user_input": {"arg": {"as_tensor": {}}}}],  # no name
        [{"user_input": {"arg": {"as_tensor": {"name": ""}}}}],
        # A user input that is not a tensor (an int or a string argument).
        [{"user_input": {"arg": {"as_int": 3}}}],
        [{"parameter": _tensor("p_w")}],  # only non-user kinds
    ],
    ids=[
        "none", "text", "mapping", "junk-entries", "junk-args", "no-name",
        "empty-name", "not-a-tensor", "no-user-kind",
    ],
)  # fmt: skip
def test_malformed_signature_entries_give_nothing(specs: object) -> None:
    inputs, outputs, provenance = _graph_io(specs, specs)
    assert (inputs, outputs, provenance) == ([], [], {})


def test_inputs_and_outputs_are_independent() -> None:
    inputs, outputs, provenance = _graph_io(
        [{"user_input": _tensor("x")}], [{"parameter": _tensor("p_w")}]
    )
    assert (inputs, outputs) == ([{"name": "x"}], [])
    assert "inputs" in provenance
    assert "outputs" not in provenance


def test_read_pt2_format_version_whitespace_only_returns_none() -> None:
    """A present ``archive_version`` file that strips to empty content is
    treated the same as an absent one (line 246's ``if arch_ver:`` false)."""
    mock_zf = MagicMock()
    mock_zf.open.return_value.__enter__.return_value.read.return_value = b"   \n"

    version, prov = _read_pt2_format_version(
        mock_zf, "", ["archive_version"], "Source: model.pt2"
    )
    assert version is None
    assert prov is None


def test_read_pt2_zip_whitespace_only_version_file_skips_provenance() -> None:
    """A present ``version`` file that strips to empty content leaves
    ``version`` and ``format_version`` unset and skips their provenance."""
    mock_zf = MagicMock()
    mock_zf.namelist.return_value = ["version"]
    mock_zf.open.return_value.__enter__.return_value.read.return_value = b"  \n"

    res = _read_pt2_zip(mock_zf, "Source: model.pt2")
    (_, _, version, _, format_version, _, provenance, _, _, _) = res
    assert version is None
    assert format_version is None
    assert "version" not in provenance
    assert "format_version" not in provenance


@pytest.mark.parametrize(
    ("model_json", "what"),
    [
        (b"[]", "model.json"),
        (b'"x"', "model.json"),
        (b'{"graph_module": []}', "graph_module"),
        (b'{"graph_module": 3}', "graph_module"),
        (b'{"graph_module": {"signature": "x"}}', "signature"),
        (b'{"graph_module": {"signature": [1]}}', "signature"),
    ],
    ids=["array", "text", "module-array", "module-int", "sig-text", "sig-array"],
)
def test_a_model_json_of_the_wrong_shape_warns_and_gives_nothing(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    model_json: bytes,
    what: str,
) -> None:
    """A part that is present but not an object is a malformed file (one
    ``WARNING:``, inputs and outputs named), not a crash."""
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(
        _make_pt2_zip({"rm/extra/name": b"m", "rm/models/model.json": model_json})
    )
    with caplog.at_level(logging.WARNING):
        meta = read_pytorch_pt2(model_file)
    assert (meta.name, meta.inputs, meta.outputs) == ("m", [], [])
    (message,) = [r.getMessage() for r in caplog.records]
    assert f"{what} is not a JSON object" in message
    assert "inputs, outputs" in message


@pytest.mark.parametrize(
    "model_json",
    [
        b"null",
        b"{}",
        b'{"graph_module": null}',
        b'{"graph_module": {"signature": null}}',
    ],
    ids=["null", "empty", "no-signature-null", "signature-null"],
)
def test_an_absent_model_json_part_is_quiet(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, model_json: bytes
) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"rm/models/model.json": model_json}))
    with caplog.at_level(logging.WARNING):
        meta = read_pytorch_pt2(model_file)
    assert (meta.inputs, meta.outputs, caplog.records) == ([], [], [])


@pytest.mark.parametrize(
    ("files", "format_version", "provenance_field"),
    [
        ({"version": b"7.3\n"}, "7.3", "version file"),
        ({"version": b"7.3", "archive_version": b"0"}, "0", "archive_version"),
        ({"version": b" \n", "archive_version": b"0"}, "0", "archive_version"),
        ({"version": b" \n"}, None, None),
    ],
    ids=["schema-only", "archive-wins", "blank-schema", "blank-only"],
)
def test_root_version_file_is_the_schema_version_not_the_model_s(
    tmp_path: Path,
    files: dict[str, bytes],
    format_version: str | None,
    provenance_field: str | None,
) -> None:
    """The root ``version`` file is a ``format_version`` fallback, never
    ``version``; ``archive_version`` is preferred when present."""
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip(files))
    meta = read_pytorch_pt2(model_file)
    assert meta.version is None
    assert "version" not in meta.provenance
    assert meta.format_info.format_version == format_version
    if provenance_field is None:
        assert "format_version" not in meta.provenance
    else:
        assert meta.provenance["format_version"].endswith(f"Field: {provenance_field}")


def test_extra_model_version_is_the_version_beside_a_root_schema_file(
    tmp_path: Path,
) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(
        _make_pt2_zip({"version": b"7.3", "extra/model_version": b"1.2"})
    )
    meta = read_pytorch_pt2(model_file)
    assert (meta.version, meta.format_info.format_version) == ("1.2", "7.3")


def test_tags_objects_and_arrays_are_canonical_json(tmp_path: Path) -> None:
    """A nested tag is written in RFC 8785 form (keys sorted, one number
    spelling), however the file spells it."""
    model_file = tmp_path / "model.pt2"
    tags = b'["a", {"z": 1.0, "b": [true, null, 1e2]}, [2, {"y": 1, "x": 0}]]'
    model_file.write_bytes(_make_pt2_zip({"mdl/extra/tags": tags}))
    meta = read_pytorch_pt2(model_file)
    assert (
        meta.properties["tags"] == 'a, {"b":[true,null,100],"z":1}, [2,{"x":0,"y":1}]'
    )


@pytest.mark.parametrize(
    ("tags", "text", "lone"),
    [
        (b'["\\ud800"]', "\\ud800", True),
        (b'[["\\ud800"]]', '["\\\\ud800"]', True),
        (b'[{"k": "\\ud800"}]', '{"k":"\\\\ud800"}', True),
        (b'[{"\\udc00": 1}]', '{"\\\\udc00":1}', True),
        (
            b'[[[{"b": ["x", "\\udfff"], "a": 1.0}], "c"]]',
            '[[{"a":1,"b":["x","\\\\udfff"]}],"c"]',
            True,
        ),
        (b'[{"z": 1.0, "b": [true]}]', '{"b":[true],"z":1}', False),
    ],
    ids=[
        "string",
        "nested-array",
        "nested-object",
        "nested-key",
        "deeper",
        "no-surrogate-canonical",
    ],
)
def test_tags_lone_surrogate_is_written_as_text_with_one_warning(
    tags: bytes,
    text: str,
    lone: bool,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A lone surrogate in a tag, nested or not, keeps the tags and the rest
    of the archive; it is written as ``\\udXXX`` and said once, as for any
    model text. A tag without one stays RFC 8785."""
    model_file = tmp_path / "model.pt2"
    buf = _io.BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(_zipfile.ZipInfo("mdl/extra/tags", (1980, 1, 1, 0, 0, 0)), tags)
    model_file.write_bytes(buf.getvalue())
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        meta = read_model_candidate(local_model_candidate(model_file))
    messages = [r.getMessage() for r in caplog.records]
    assert not [m for m in messages if "failed to extract" in m]
    assert meta.properties["tags"] == text
    assert "archive_contents" in meta.properties
    assert len([m for m in messages if "lone surrogates" in m]) == int(lone)
