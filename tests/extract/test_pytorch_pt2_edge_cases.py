# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Edge-case tests for the PyTorch PT2 Archive metadata extractor.

See also: :mod:`tests.extract.test_pytorch_pt2` for the primary mocked and
integration test suite this file was split out of to stay under the
project's file-size limit.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import io as _io
import json as _json
import zipfile as _zipfile
from unittest.mock import MagicMock

from pitloom.extract._pytorch_pt2 import (
    _read_pt2_format_version,
    _read_pt2_graph_io,
    _read_pt2_zip,
)


def _make_pt2_zip(files: dict[str, bytes] | None = None) -> bytes:
    """Build a minimal in-memory ZIP archive for PT2 Archive testing."""
    buf = _io.BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        for name, data in (files or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_read_pt2_graph_io_skips_unresolvable_entries_then_matches() -> None:
    """_read_pt2_graph_io skips a non-dict entry and a dict missing
    ``as_tensor.name`` before finding a valid entry, and records no
    provenance when neither inputs nor outputs are found for a side."""
    graph = {
        "graph_module": {
            "graph": {
                "inputs": [
                    "not-a-dict",
                    {"as_tensor": {}},
                    {"as_tensor": {"name": "x"}},
                ],
                "outputs": [],
            }
        }
    }
    buf = _make_pt2_zip({"models/model.json": _json.dumps(graph).encode()})
    with _zipfile.ZipFile(_io.BytesIO(buf)) as zf:
        provenance: dict[str, str] = {}
        inputs, outputs = _read_pt2_graph_io(zf, "", "Source: model.pt2", provenance)

    assert inputs == [{"name": "x"}]
    assert outputs == []
    assert "inputs" in provenance
    assert "outputs" not in provenance


def test_read_pt2_graph_io_empty_inputs_with_populated_outputs() -> None:
    """No inputs found (line 228's ``if inputs:`` false) while outputs are
    still recorded normally."""
    graph = {
        "graph_module": {
            "graph": {
                "inputs": [],
                "outputs": [{"as_tensor": {"name": "y"}}],
            }
        }
    }
    buf = _make_pt2_zip({"models/model.json": _json.dumps(graph).encode()})
    with _zipfile.ZipFile(_io.BytesIO(buf)) as zf:
        provenance: dict[str, str] = {}
        inputs, outputs = _read_pt2_graph_io(zf, "", "Source: model.pt2", provenance)

    assert inputs == []
    assert outputs == [{"name": "y"}]
    assert "inputs" not in provenance
    assert "outputs" in provenance


def test_read_pt2_format_version_whitespace_only_returns_none() -> None:
    """A present ``archive_version`` file that strips to empty content is
    treated the same as an absent one (line 246's ``if arch_ver:`` false)."""
    mock_zf = MagicMock()
    mock_zf.read.return_value = b"   \n"

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
    mock_zf.read.return_value = b"  \n"

    res = _read_pt2_zip(mock_zf, "Source: model.pt2")
    (_, version, _, _, _, _, provenance, _, _) = res
    assert version is None
    assert "version" not in provenance
