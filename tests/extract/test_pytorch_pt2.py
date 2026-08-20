# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the PyTorch PT2 Archive metadata extractor (.pt2).

Covers mocked and integration tests.

See also: :mod:`tests.extract.test_pytorch_pt2_edge_cases` for graph-io,
format-version, and version-file edge cases split out to stay under the
project's file-size limit.
"""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

import io as _io
import json as _json
import logging
import zipfile as _zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract._pytorch_pt2 import (
    _detect_root_prefix,
    _read_pt2_extra_files,
    _read_pt2_meta_entry,
    _read_pt2_zip,
)
from pitloom.extract.ai_model import read_pytorch_pt2

# ---------------------------------------------------------------------------
# PT2 Archive extractor (mocked / stdlib ZIP)
# ---------------------------------------------------------------------------

_PT2_DIR = Path(__file__).parent.parent / "fixtures" / "aimodels" / "pytorch_pt2"


def _make_pt2_zip(
    files: dict[str, bytes] | None = None,
) -> bytes:
    """Build a minimal in-memory ZIP archive for PT2 Archive testing."""
    buf = _io.BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        for name, data in (files or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_read_pytorch_pt2_format(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"version": b"2\n"}))
    meta = read_pytorch_pt2(model_file)
    assert meta.format_info.model_format == AiModelFormat.PYTORCH_PT2


def test_read_pytorch_pt2_version_file(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"version": b"2\n"}))
    meta = read_pytorch_pt2(model_file)
    assert meta.version == "2"
    assert "version" in meta.provenance


def test_read_pytorch_pt2_archive_contents_in_properties(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"version": b"2", "model.pte": b"\x00" * 8}))
    meta = read_pytorch_pt2(model_file)
    assert "archive_contents" in meta.properties
    assert "version" in meta.properties["archive_contents"]


def test_read_pytorch_pt2_metadata_json_name(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    metadata = _json.dumps({"name": "my_pt2_model"}).encode()
    model_file.write_bytes(_make_pt2_zip({"version": b"2", "METADATA.json": metadata}))
    meta = read_pytorch_pt2(model_file)
    assert meta.name == "my_pt2_model"
    assert "name" in meta.provenance


def test_read_pytorch_pt2_metadata_json_model_name_fallback(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    metadata = _json.dumps({"model_name": "fallback_name"}).encode()
    model_file.write_bytes(_make_pt2_zip({"version": b"2", "METADATA.json": metadata}))
    meta = read_pytorch_pt2(model_file)
    assert meta.name == "fallback_name"


def test_read_pytorch_pt2_no_metadata_json_name_is_none(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"version": b"2"}))
    meta = read_pytorch_pt2(model_file)
    assert meta.name is None


def test_read_pytorch_pt2_no_version_file(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"model.pte": b"\x00" * 4}))
    meta = read_pytorch_pt2(model_file)
    assert meta.version is None


def test_read_pytorch_pt2_not_a_zip_raises(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(b"not a zip file")
    with pytest.raises(ValueError, match="PT2 Archive must be a ZIP"):
        read_pytorch_pt2(model_file)


def test_read_pytorch_pt2_no_type_of_model(tmp_path: Path) -> None:
    # PT2 Archive does not inspect pickle; type_of_model is always None.
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"version": b"2"}))
    meta = read_pytorch_pt2(model_file)
    assert meta.type_of_model is None


def test_read_pytorch_pt2_extra_description(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"mdl/extra/description": b"A test model."}))
    meta = read_pytorch_pt2(model_file)
    assert meta.description == "A test model."
    assert "description" in meta.provenance


def test_read_pytorch_pt2_extra_model_version(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"mdl/extra/model_version": b"2.3.1"}))
    meta = read_pytorch_pt2(model_file)
    assert meta.version == "2.3.1"


def test_read_pytorch_pt2_extra_version_preferred_over_archive_version(
    tmp_path: Path,
) -> None:
    # extra/model_version (semantic model version) wins over archive_version
    # (which becomes format_version, not model version).
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(
        _make_pt2_zip(
            {
                "mdl/archive_version": b"0",
                "mdl/extra/model_version": b"1.0.0",
            }
        )
    )
    meta = read_pytorch_pt2(model_file)
    assert meta.version == "1.0.0"
    assert meta.format_info.format_version == "0"
    assert "archive_version" not in meta.properties


def test_read_pytorch_pt2_extra_license(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"mdl/extra/license": b"Apache-2.0"}))
    meta = read_pytorch_pt2(model_file)
    assert meta.license == "Apache-2.0"


def test_read_pytorch_pt2_extra_author_in_properties(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"mdl/extra/author": b"Alice"}))
    meta = read_pytorch_pt2(model_file)
    assert meta.properties.get("author") == "Alice"


def test_read_pytorch_pt2_extra_tags_json_array(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(
        _make_pt2_zip({"mdl/extra/tags": _json.dumps(["a", "b"]).encode()})
    )
    meta = read_pytorch_pt2(model_file)
    assert meta.properties.get("tags") == "a, b"


def test_read_pytorch_pt2_malformed_metadata_json_logs_and_name_is_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Invalid JSON in METADATA.json is caught, logged, and name falls back
    to None (same behaviour as a METADATA.json without a name field)."""
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(
        _make_pt2_zip({"version": b"2", "METADATA.json": b"{not valid json"})
    )
    with caplog.at_level(logging.DEBUG, logger="pitloom.extract._pytorch_pt2"):
        meta = read_pytorch_pt2(model_file)
    assert meta.name is None
    assert any("METADATA.json" in r.message for r in caplog.records)


def test_read_pytorch_pt2_malformed_extra_tags_logs_and_keeps_raw_value(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """extra/tags content that isn't valid JSON is caught, logged, and the
    raw string is kept as-is (same fallback behaviour as before logging)."""
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"mdl/extra/tags": b"not a json array"}))
    with caplog.at_level(logging.DEBUG, logger="pitloom.extract._pytorch_pt2"):
        meta = read_pytorch_pt2(model_file)
    assert meta.properties.get("tags") == "not a json array"
    assert any(
        "Failed to parse PT2 extra/tags as JSON" in r.message for r in caplog.records
    )


def test_read_pytorch_pt2_malformed_model_json_logs_and_returns_empty_io(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Invalid JSON in models/model.json is caught, logged, and inputs/outputs
    fall back to empty lists (same as when the file is absent)."""
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"mdl/models/model.json": b"{not valid json"}))
    with caplog.at_level(logging.DEBUG, logger="pitloom.extract._pytorch_pt2"):
        meta = read_pytorch_pt2(model_file)
    assert meta.inputs == []
    assert meta.outputs == []
    assert any("models/model.json" in r.message for r in caplog.records)


def test_read_pt2_extra_files_read_failure_logs_and_returns_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A ZIP member listed in the archive that fails to read (e.g. a
    corrupt/encrypted entry) is caught, logged, and treated the same as a
    missing extra/name file (falls back to None)."""
    mock_zf = MagicMock()
    mock_zf.namelist.return_value = ["extra/name"]
    mock_zf.read.side_effect = RuntimeError("bad CRC-32")

    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}
    with caplog.at_level(logging.DEBUG, logger="pitloom.extract._pytorch_pt2"):
        name, description, version, license_expr = _read_pt2_extra_files(
            mock_zf, "", "Source: model.pt2", properties, provenance
        )

    assert name is None
    assert description is None
    assert version is None
    assert license_expr is None
    assert "name" not in provenance
    assert any("extra/name" in r.message for r in caplog.records)


def test_read_pt2_zip_archive_version_read_failure_logs_and_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A ZIP member listed in the archive that fails to read while resolving
    archive_version is caught, logged, and format_version falls back to
    None instead of raising."""
    mock_zf = MagicMock()
    mock_zf.namelist.return_value = ["archive_version"]
    mock_zf.read.side_effect = RuntimeError("bad CRC-32")

    with caplog.at_level(logging.DEBUG, logger="pitloom.extract._pytorch_pt2"):
        result = _read_pt2_zip(mock_zf, "Source: model.pt2")

    (_, _, _, _, format_version, _, provenance, _, _) = result
    assert format_version is None
    assert "format_version" not in provenance
    assert any("archive_version" in r.message for r in caplog.records)


def test_read_pytorch_pt2_model_json_inputs_outputs(tmp_path: Path) -> None:
    graph = {
        "graph_module": {
            "graph": {
                "inputs": [{"as_tensor": {"name": "x"}}],
                "outputs": [{"as_tensor": {"name": "out"}}],
            }
        }
    }
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(
        _make_pt2_zip({"mdl/models/model.json": _json.dumps(graph).encode()})
    )
    meta = read_pytorch_pt2(model_file)
    assert meta.inputs == [{"name": "x"}]
    assert meta.outputs == [{"name": "out"}]
    assert "inputs" in meta.provenance
    assert "outputs" in meta.provenance


# ---------------------------------------------------------------------------
# Integration tests -- PT2 Archive fixtures (pytorch_pt2/*.pt2)
# Require: fixture files present
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pt2_fixture() -> Any:
    pt2_files = list(_PT2_DIR.glob("*.pt2"))
    if not pt2_files:
        pytest.skip(
            "No .pt2 fixture files found in tests/fixtures/aimodels/pytorch_pt2/"
        )
    return read_pytorch_pt2(pt2_files[0])


def test_pt2_fixture_format(pt2_fixture: Any) -> None:
    assert pt2_fixture.format_info.model_format == AiModelFormat.PYTORCH_PT2


def test_pt2_fixture_description(pt2_fixture: Any) -> None:
    assert (
        pt2_fixture.description
        == "A serialized PT2 model for metadata extraction test."
    )


def test_pt2_fixture_version(pt2_fixture: Any) -> None:
    assert pt2_fixture.version == "1.0.0"


def test_pt2_fixture_license(pt2_fixture: Any) -> None:
    assert pt2_fixture.license == "CC0-1.0"


def test_pt2_fixture_author_in_properties(pt2_fixture: Any) -> None:
    assert pt2_fixture.properties.get("author") == "Pitloom"


def test_pt2_fixture_tags_in_properties(pt2_fixture: Any) -> None:
    assert "regression" in pt2_fixture.properties.get("tags", "")


def test_pt2_fixture_inputs(pt2_fixture: Any) -> None:
    assert len(pt2_fixture.inputs) > 0
    input_names = {inp["name"] for inp in pt2_fixture.inputs}
    assert "x" in input_names


def test_pt2_fixture_outputs(pt2_fixture: Any) -> None:
    assert len(pt2_fixture.outputs) > 0
    assert pt2_fixture.outputs[0]["name"] == "linear"


def test_detect_root_prefix_edge_cases() -> None:
    """_detect_root_prefix handles empty lists and archives without common root."""
    assert _detect_root_prefix([]) == ""
    assert _detect_root_prefix(["model_a/weights.bin", "model_b/weights.bin"]) == ""
    assert _detect_root_prefix(["root_file.txt", "other.txt"]) == ""


def test_read_pt2_meta_entry_model_name_and_invalid_json() -> None:
    """_read_pt2_meta_entry parses model_name key and handles invalid JSON."""
    mock_zf = MagicMock()
    mock_zf.read.return_value = b'{"model_name": "exec_model"}'
    name, prov = _read_pt2_meta_entry(mock_zf, "METADATA.json", "Source: test.pt2")
    assert name == "exec_model"
    assert prov is not None and "METADATA.json.model_name" in prov

    # Non-dict JSON
    mock_zf.read.return_value = b'["not", "a", "dict"]'
    name2, prov2 = _read_pt2_meta_entry(mock_zf, "METADATA.json", "Source: test.pt2")
    assert name2 is None
    assert prov2 is None


def test_read_pt2_zip_large_file_list() -> None:
    """_read_pt2_zip summarizes archive contents when > 20 members are present."""
    mock_zf = MagicMock()
    mock_zf.namelist.return_value = [f"entry_{i}.bin" for i in range(25)]
    mock_zf.read.return_value = b""

    res = _read_pt2_zip(mock_zf, "Source: test.pt2")
    properties = res[5]
    assert "... (25 total)" in properties["archive_contents"]


def test_read_pytorch_pt2_is_zipfile_oserror(tmp_path: Path) -> None:
    """read_pytorch_pt2 raises ValueError when is_zipfile encounters an OSError."""
    fake_pt2 = tmp_path / "corrupt.pt2"
    fake_pt2.write_bytes(b"dummy")

    with patch("zipfile.is_zipfile", side_effect=OSError("IO failure")):
        with pytest.raises(ValueError, match="Failed to open PT2 Archive"):
            read_pytorch_pt2(fake_pt2)


def test_read_pt2_extra_tags_string_fallback() -> None:
    """_read_pt2_extra_files handles non-JSON list extra/tags gracefully."""
    mock_zf = MagicMock()
    mock_zf.namelist.return_value = ["extra/tags"]

    # 1. Valid JSON that is not a list (e.g. dict)
    mock_zf.read.return_value = b'{"not_a_list": true}'
    props: dict[str, str] = {}
    prov: dict[str, str] = {}
    _read_pt2_extra_files(mock_zf, "", "Source: test.pt2", props, prov)
    assert props.get("tags") == '{"not_a_list": true}'

    # 2. Invalid JSON string
    mock_zf.read.return_value = b"plain_tag_string"
    props2: dict[str, str] = {}
    prov2: dict[str, str] = {}
    _read_pt2_extra_files(mock_zf, "", "Source: test.pt2", props2, prov2)
    assert props2.get("tags") == "plain_tag_string"


def test_read_pt2_meta_entry_empty_dict() -> None:
    """_read_pt2_meta_entry returns None when JSON dict lacks name/model_name."""
    mock_zf = MagicMock()
    mock_zf.read.return_value = b'{"other_key": "val"}'
    name, prov = _read_pt2_meta_entry(mock_zf, "metadata.json", "Source: test.pt2")
    assert name is None
    assert prov is None


def test_read_pt2_zip_rich_metadata_combination() -> None:
    """_read_pt2_zip parses root version, archive_version, extra/name, and graph io."""
    zip_bytes = _make_pt2_zip(
        {
            "version": b"0.9.0",
            "archive_version": b"2.1.0",
            "extra/name": b"overridden_name",
            "extra/description": b"A rich model",
            "models/model.json": _json.dumps(
                {
                    "graph_module": {
                        "graph": {
                            "inputs": [
                                "not_a_dict",
                                {"as_tensor": {"name": "tensor_in"}},
                            ],
                            "outputs": [{"as_tensor": {"name": "tensor_out"}}],
                        }
                    }
                }
            ).encode("utf-8"),
        }
    )
    zf = _zipfile.ZipFile(_io.BytesIO(zip_bytes))
    res = _read_pt2_zip(zf, "Source: test.pt2")

    name = res[0]
    description = res[1]
    version = res[2]
    format_version = res[4]
    inputs = res[7]
    outputs = res[8]

    assert name == "overridden_name"
    assert description == "A rich model"
    assert version == "0.9.0"
    assert format_version == "2.1.0"
    assert len(inputs) == 1
    assert inputs[0]["name"] == "tensor_in"
    assert len(outputs) == 1
    assert outputs[0]["name"] == "tensor_out"
