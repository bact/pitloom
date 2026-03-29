# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the PyTorch PT2 Archive metadata extractor (.pt2).

Covers mocked and integration tests.
"""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

import io as _io
import json as _json
import zipfile as _zipfile
from pathlib import Path
from typing import Any

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import read_pytorch_pt2

# ---------------------------------------------------------------------------
# PT2 Archive extractor (mocked / stdlib ZIP)
# ---------------------------------------------------------------------------

_PT2_DIR = Path(__file__).parent / "fixtures" / "pytorch_pt2"


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
    assert meta.format == AiModelFormat.PYTORCH_PT2


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
    # extra/model_version (semantic) wins over archive_version (format version).
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
    assert meta.properties.get("archive_version") == "0"


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
# Integration tests — PT2 Archive fixtures (pytorch_pt2/*.pt2)
# Require: fixture files present
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pt2_fixture() -> Any:
    pt2_files = list(_PT2_DIR.glob("*.pt2"))
    if not pt2_files:
        pytest.skip("No .pt2 fixture files found in tests/fixtures/pytorch_pt2/")
    return read_pytorch_pt2(pt2_files[0])


def test_pt2_fixture_format(pt2_fixture: Any) -> None:
    assert pt2_fixture.format == AiModelFormat.PYTORCH_PT2


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
