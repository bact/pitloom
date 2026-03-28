# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for format detection, magic-byte sniffing, read_ai_model dispatch,
FormatInfo/REGISTRY, and the AiModelMetadata dataclass."""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.extract.ai_model import (
    REGISTRY,
    FormatInfo,
    _sniff_format,
    detect_ai_model_format,
    read_ai_model,
)


def _magic(fmt: AiModelFormat) -> bytes:
    """Look up the magic bytes for *fmt* from the registry."""
    info = next((i for i in REGISTRY if i.format == fmt), None)
    assert info is not None and info.magic is not None, f"No magic for {fmt}"
    return info.magic


# ---------------------------------------------------------------------------
# FormatInfo dataclass
# ---------------------------------------------------------------------------


def test_format_info_is_frozen() -> None:
    info = next(i for i in REGISTRY if i.format == AiModelFormat.GGUF)
    with pytest.raises((AttributeError, TypeError)):
        info.magic = b"X"  # type: ignore[misc]


def test_format_info_fasttext() -> None:
    info = next(i for i in REGISTRY if i.format == AiModelFormat.FASTTEXT)
    assert info.magic == b"\xba\x16\x4f\x2f"
    assert ".ftz" in info.extensions
    assert info.reader is not None


def test_format_info_gguf() -> None:
    info = next(i for i in REGISTRY if i.format == AiModelFormat.GGUF)
    assert info.magic == b"GGUF"
    assert ".gguf" in info.extensions
    assert info.reader is not None


def test_format_info_hdf5() -> None:
    info = next(i for i in REGISTRY if i.format == AiModelFormat.HDF5)
    assert info.magic == b"\x89HDF\r\n\x1a\n"
    assert ".h5" in info.extensions
    assert ".hdf5" in info.extensions
    assert info.reader is not None


def test_format_info_numpy() -> None:
    info = next(i for i in REGISTRY if i.format == AiModelFormat.NUMPY)
    assert info.magic == b"\x93NUMPY"
    assert ".npy" in info.extensions
    assert ".npz" in info.extensions
    assert info.reader is not None


def test_format_info_onnx() -> None:
    info = next(i for i in REGISTRY if i.format == AiModelFormat.ONNX)
    assert info.magic is None
    assert ".onnx" in info.extensions
    assert info.reader is not None


def test_format_info_pt2() -> None:
    info = next(i for i in REGISTRY if i.format == AiModelFormat.PYTORCH_PT2)
    assert info.magic is None
    assert ".pt2" in info.extensions
    assert ".pt" not in info.extensions
    assert info.reader is not None


def test_format_info_pytorch() -> None:
    info = next(i for i in REGISTRY if i.format == AiModelFormat.PYTORCH)
    assert info.magic is None
    assert ".pt" in info.extensions
    assert ".pth" in info.extensions
    assert ".pt2" not in info.extensions
    assert info.reader is not None


def test_format_info_safetensors() -> None:
    info = next(i for i in REGISTRY if i.format == AiModelFormat.SAFETENSORS)
    assert info.magic is None
    assert ".safetensors" in info.extensions
    assert info.reader is not None


# ---------------------------------------------------------------------------
# REGISTRY integrity
# ---------------------------------------------------------------------------


def test_registry_covers_all_non_unknown_formats() -> None:
    registry_formats = {info.format for info in REGISTRY}
    all_formats = {f for f in AiModelFormat if f != AiModelFormat.UNKNOWN}
    assert registry_formats == all_formats


def test_registry_extensions_are_lowercase_with_dot() -> None:
    for info in REGISTRY:
        for ext in info.extensions:
            assert ext.startswith("."), f"{ext!r} missing leading dot"
            assert ext == ext.lower(), f"{ext!r} is not lowercase"


def test_registry_no_duplicate_extensions() -> None:
    seen: dict[str, AiModelFormat] = {}
    for info in REGISTRY:
        for ext in info.extensions:
            assert ext not in seen, (
                f"{ext!r} registered for both {seen[ext]} and {info.format}"
            )
            seen[ext] = info.format


def test_registry_all_readers_are_callable() -> None:
    for info in REGISTRY:
        assert callable(info.reader), f"{info.format} has no callable reader"


# ---------------------------------------------------------------------------
# detect_ai_model_format
# ---------------------------------------------------------------------------


def test_detect_format_onnx() -> None:
    assert detect_ai_model_format(Path("model.onnx")) == AiModelFormat.ONNX


def test_detect_format_safetensors() -> None:
    assert (
        detect_ai_model_format(Path("weights.safetensors")) == AiModelFormat.SAFETENSORS
    )


def test_detect_format_gguf() -> None:
    assert detect_ai_model_format(Path("llama.gguf")) == AiModelFormat.GGUF


def test_detect_format_unknown() -> None:
    assert detect_ai_model_format(Path("model.pkl")) == AiModelFormat.UNKNOWN


def test_detect_format_case_insensitive() -> None:
    assert detect_ai_model_format(Path("MODEL.ONNX")) == AiModelFormat.ONNX


def test_detect_format_fasttext_ftz() -> None:
    assert detect_ai_model_format(Path("model.ftz")) == AiModelFormat.FASTTEXT


def test_detect_format_bin_without_file_is_unknown() -> None:
    # .bin has no extension entry; non-existent path → UNKNOWN (no magic sniff).
    assert detect_ai_model_format(Path("model.bin")) == AiModelFormat.UNKNOWN


# ---------------------------------------------------------------------------
# Magic-byte sniffing (_sniff_format / detect_ai_model_format with real files)
# ---------------------------------------------------------------------------


def test_sniff_gguf_magic(tmp_path: Path) -> None:
    f = tmp_path / "model.bin"  # wrong extension — magic wins
    f.write_bytes(_magic(AiModelFormat.GGUF) + b"\x00" * 20)
    assert detect_ai_model_format(f) == AiModelFormat.GGUF


def test_sniff_fasttext_magic(tmp_path: Path) -> None:
    f = tmp_path / "model.bin"
    f.write_bytes(_magic(AiModelFormat.FASTTEXT) + b"\x00" * 20)
    assert detect_ai_model_format(f) == AiModelFormat.FASTTEXT


def test_sniff_safetensors_magic(tmp_path: Path) -> None:
    # Construct a minimal Safetensors header: 8-byte LE size + JSON opening brace.
    header_json = b'{"__metadata__":{}}'
    size_bytes = len(header_json).to_bytes(8, byteorder="little")
    f = tmp_path / "model.bin"
    f.write_bytes(size_bytes + header_json)
    assert detect_ai_model_format(f) == AiModelFormat.SAFETENSORS


def test_sniff_unknown_returns_extension_fallback(tmp_path: Path) -> None:
    # Unrecognised magic + .onnx extension → extension fallback gives ONNX.
    f = tmp_path / "model.onnx"
    f.write_bytes(b"\x08\x01\x12\x04" + b"\x00" * 20)  # typical protobuf, no magic
    assert detect_ai_model_format(f) == AiModelFormat.ONNX


def test_sniff_empty_file_falls_back_to_extension(tmp_path: Path) -> None:
    f = tmp_path / "model.ftz"
    f.write_bytes(b"")
    assert detect_ai_model_format(f) == AiModelFormat.FASTTEXT


def test_sniff_format_direct_gguf(tmp_path: Path) -> None:
    f = tmp_path / "x"
    f.write_bytes(_magic(AiModelFormat.GGUF) + b"\x00" * 5)
    assert _sniff_format(f) == AiModelFormat.GGUF


def test_sniff_format_direct_fasttext(tmp_path: Path) -> None:
    f = tmp_path / "x"
    f.write_bytes(_magic(AiModelFormat.FASTTEXT) + b"\x00" * 5)
    assert _sniff_format(f) == AiModelFormat.FASTTEXT


def test_sniff_format_nonexistent_returns_unknown() -> None:
    assert _sniff_format(Path("/no/such/file")) == AiModelFormat.UNKNOWN


def test_sniff_numpy_npy_magic(tmp_path: Path) -> None:
    f = tmp_path / "array.bin"  # wrong extension — magic wins
    f.write_bytes(_magic(AiModelFormat.NUMPY) + b"\x00" * 20)
    assert detect_ai_model_format(f) == AiModelFormat.NUMPY


def test_sniff_hdf5_magic(tmp_path: Path) -> None:
    f = tmp_path / "model.bin"  # wrong extension — magic wins
    f.write_bytes(_magic(AiModelFormat.HDF5) + b"\x00" * 20)
    assert detect_ai_model_format(f) == AiModelFormat.HDF5


# ---------------------------------------------------------------------------
# detect_ai_model_format — new formats (extension-based)
# ---------------------------------------------------------------------------


def test_detect_format_numpy_npy() -> None:
    assert detect_ai_model_format(Path("array.npy")) == AiModelFormat.NUMPY


def test_detect_format_numpy_npz() -> None:
    assert detect_ai_model_format(Path("arrays.npz")) == AiModelFormat.NUMPY


def test_detect_format_hdf5_h5() -> None:
    assert detect_ai_model_format(Path("model.h5")) == AiModelFormat.HDF5


def test_detect_format_hdf5_hdf5() -> None:
    assert detect_ai_model_format(Path("model.hdf5")) == AiModelFormat.HDF5


def test_detect_format_pytorch_pt() -> None:
    assert detect_ai_model_format(Path("model.pt")) == AiModelFormat.PYTORCH


def test_detect_format_pytorch_pth() -> None:
    assert detect_ai_model_format(Path("model.pth")) == AiModelFormat.PYTORCH


def test_detect_format_pytorch_pt2() -> None:
    assert detect_ai_model_format(Path("model.pt2")) == AiModelFormat.PYTORCH_PT2


# ---------------------------------------------------------------------------
# read_ai_model — dispatch
# ---------------------------------------------------------------------------


def test_extract_metadata_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        read_ai_model(Path("/nonexistent/model.onnx"))


def test_extract_metadata_unsupported_format(tmp_path: Path) -> None:
    model_file = tmp_path / "model.xyz"
    model_file.write_bytes(b"unknown format")
    with pytest.raises(ValueError, match="Unsupported model format"):
        read_ai_model(model_file)


# ---------------------------------------------------------------------------
# AiModelMetadata dataclass
# ---------------------------------------------------------------------------


def test_ai_model_metadata_defaults() -> None:
    meta = AiModelMetadata()
    assert meta.format == AiModelFormat.UNKNOWN
    assert meta.name is None
    assert meta.hyperparameters == {}
    assert meta.properties == {}
    assert meta.inputs == []
    assert meta.outputs == []
    assert meta.provenance == {}


def test_ai_model_metadata_construction() -> None:
    meta = AiModelMetadata(
        format=AiModelFormat.ONNX,
        name="MyModel",
        version="1.0",
        type_of_model="transformer",
        hyperparameters={"num_heads": 12},
        provenance={"name": "Source: model.onnx | Field: graph.name"},
    )
    assert meta.format == AiModelFormat.ONNX
    assert meta.name == "MyModel"
    assert meta.hyperparameters["num_heads"] == 12
    assert "name" in meta.provenance


# ---------------------------------------------------------------------------
# FormatInfo type annotation
# ---------------------------------------------------------------------------


def test_format_info_is_format_info_type() -> None:
    for info in REGISTRY:
        assert isinstance(info, FormatInfo)
