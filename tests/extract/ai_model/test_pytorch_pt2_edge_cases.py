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
import zipfile as _zipfile
from unittest.mock import MagicMock

import pytest

from pitloom.extract.ai_model.pytorch_pt2 import (
    _read_pt2_format_version,
    _read_pt2_graph_io,
    _read_pt2_zip,
)

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
    ``version`` unset and skips its provenance entry (line 300)."""
    mock_zf = MagicMock()
    mock_zf.namelist.return_value = ["version"]
    mock_zf.open.return_value.__enter__.return_value.read.return_value = b"  \n"

    res = _read_pt2_zip(mock_zf, "Source: model.pt2")
    (_, _, version, _, _, _, provenance, _, _, _) = res
    assert version is None
    assert "version" not in provenance
