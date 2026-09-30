# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for header-based format detection and the header reader.

One format authority for path and header callers: magic beats extension,
absence is not an error, a real access failure is.

See also: :mod:`tests.extract.ai_model.test_ai_model`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import (
    SNIFF_BYTES,
    detect_ai_model_format,
    detect_ai_model_format_from_header,
    read_ai_model,
    read_ai_model_header,
)


def _magic(fmt: AiModelFormat) -> bytes:
    assert fmt.magic is not None, f"No magic for {fmt}"
    return fmt.magic


_AIMODELS = Path(__file__).parent.parent.parent / "fixtures" / "aimodels"


def _fixture(rel: str) -> Callable[[Path], Path]:
    return lambda _tmp: _AIMODELS / rel


def _gguf_as_onnx(tmp: Path) -> Path:
    f = tmp / "x.onnx"
    f.write_bytes(_magic(AiModelFormat.GGUF) + b"\x00" * 20)
    return f


def _text_bin(tmp: Path) -> Path:
    f = tmp / "notes.bin"
    f.write_text("just some notes", encoding="utf-8")
    return f


def _empty_ftz(tmp: Path) -> Path:
    f = tmp / "model.ftz"
    f.write_bytes(b"")
    return f


def _missing_onnx(tmp: Path) -> Path:
    return tmp / "missing.onnx"


def _dir_onnx(tmp: Path) -> Path:
    d = tmp / "d.onnx"
    d.mkdir()
    return d


@pytest.mark.parametrize(
    ("path_factory", "expected"),
    [
        (_fixture("fasttext/lid.176.ftz"), AiModelFormat.FASTTEXT),
        (_fixture("gguf/stories260K.gguf"), AiModelFormat.GGUF),
        (_fixture("hdf5/example-model.h5"), AiModelFormat.HDF5),
        (_fixture("numpy/example-model-v1.npy"), AiModelFormat.NUMPY),
        (
            _fixture("safetensors/phi-tiny-random.safetensors"),
            AiModelFormat.SAFETENSORS,
        ),
        (_fixture("onnx/light-inception-v2.onnx"), AiModelFormat.ONNX),
        (_fixture("keras/example-model.keras"), AiModelFormat.KERAS),
        (_fixture("pytorch/example-model.pt"), AiModelFormat.PYTORCH),
        (_fixture("pytorch_pt2/example-model.pt2"), AiModelFormat.PYTORCH_PT2),
        (_fixture("numpy/example-model-bundle.npz"), AiModelFormat.NUMPY),
        (_fixture("fasttext/sentimentdemo.bin"), AiModelFormat.FASTTEXT),
        (_gguf_as_onnx, AiModelFormat.GGUF),
        (_text_bin, AiModelFormat.UNKNOWN),
        (_empty_ftz, AiModelFormat.FASTTEXT),
        (_missing_onnx, AiModelFormat.ONNX),
        (_dir_onnx, AiModelFormat.ONNX),
    ],
)
def test_detect_from_header_agrees_with_path_detection(
    tmp_path: Path,
    path_factory: Callable[[Path], Path],
    expected: AiModelFormat,
) -> None:
    p = path_factory(tmp_path)
    header = b""
    if p.is_file():
        with p.open("rb") as fh:
            header = fh.read(SNIFF_BYTES)
    assert detect_ai_model_format(p) == expected
    assert detect_ai_model_format_from_header(header, p.name) == expected


def _st_header(size: int, brace: bytes = b"{") -> bytes:
    return size.to_bytes(8, "little") + brace


_GGUF, _NPY, _FT = (
    _magic(f) for f in (AiModelFormat.GGUF, AiModelFormat.NUMPY, AiModelFormat.FASTTEXT)
)


@pytest.mark.parametrize(
    ("header", "name", "expected"),
    [
        # magic beats a disagreeing extension, in both directions
        (_GGUF + b"\0" * 5, "x.npy", AiModelFormat.GGUF),
        (_NPY + b"\0" * 5, "x.bin", AiModelFormat.NUMPY),
        (_FT + b"\0" * 5, "", AiModelFormat.FASTTEXT),
        (_GGUF, "x.onnx", AiModelFormat.GGUF),
        # a truncated magic is no magic: extension decides
        (_GGUF[:-1], "x.gguf", AiModelFormat.GGUF),
        (_GGUF[:-1], "x.bin", AiModelFormat.UNKNOWN),
        (_NPY[:-1], "x.npy", AiModelFormat.NUMPY),
        # extension: case-insensitive, last suffix only, POSIX names only
        (b"", "x.NPY", AiModelFormat.NUMPY),
        (b"", "model.tar.npy", AiModelFormat.NUMPY),
        (b"", "model.npy.bak", AiModelFormat.UNKNOWN),
        (b"", "d.npy/file", AiModelFormat.UNKNOWN),
        (b"", ".npy", AiModelFormat.UNKNOWN),
        (b"", "my model \u00e9.onnx", AiModelFormat.ONNX),
        (b"", "a\\b.pt", AiModelFormat.PYTORCH),
        (b"", "x.bin", AiModelFormat.UNKNOWN),
        # Safetensors heuristic: needs all 9 bytes, 0 < size < 100 MB, then "{"
        (_st_header(19), "x.bin", AiModelFormat.SAFETENSORS),
        (_st_header(99_999_999), "x.bin", AiModelFormat.SAFETENSORS),
        (_st_header(100_000_000), "x.bin", AiModelFormat.UNKNOWN),
        (_st_header(0), "x.bin", AiModelFormat.UNKNOWN),
        (_st_header(19, b"["), "x.bin", AiModelFormat.UNKNOWN),
        (_st_header(19)[:8], "x.bin", AiModelFormat.UNKNOWN),
        (_st_header(19)[:8], "x.safetensors", AiModelFormat.SAFETENSORS),
    ],
)
def test_detect_from_header(header: bytes, name: str, expected: AiModelFormat) -> None:
    assert detect_ai_model_format_from_header(header, name) == expected


@pytest.mark.parametrize(
    "size", [0, 3, SNIFF_BYTES - 1, SNIFF_BYTES, SNIFF_BYTES + 1, 100]
)
def test_read_ai_model_header_is_capped_prefix(tmp_path: Path, size: int) -> None:
    f = tmp_path / "f.bin"
    data = bytes(range(size))
    f.write_bytes(data)
    assert read_ai_model_header(f) == data[:SNIFF_BYTES]


def test_read_ai_model_header_absence_is_empty(tmp_path: Path) -> None:
    (tmp_path / "file").write_bytes(b"x")
    for absent in (tmp_path, tmp_path / "missing.bin", tmp_path / "file" / "child"):
        assert read_ai_model_header(absent) == b""


@pytest.mark.parametrize(("is_dir", "raises"), [(True, False), (False, True)])
def test_read_ai_model_header_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, is_dir: bool, raises: bool
) -> None:
    """``PermissionError`` on a directory is absence (Windows raises it
    there); on a file it is a real denial and must propagate."""
    target = tmp_path if is_dir else tmp_path / "f.onnx"
    if not is_dir:
        target.write_bytes(b"x")

    def _deny(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(13, "denied")

    monkeypatch.setattr(Path, "open", _deny)
    if raises:
        with pytest.raises(PermissionError):
            read_ai_model_header(target)
        # path-based detection never raises: it falls back to the extension
        assert detect_ai_model_format(target) == AiModelFormat.ONNX
    else:
        assert read_ai_model_header(target) == b""


def test_read_ai_model_uses_given_format(tmp_path: Path) -> None:
    pytest.importorskip("onnx")
    p = tmp_path / "weights.dat"
    shutil.copyfile(_AIMODELS / "onnx" / "light-inception-v2.onnx", p)
    with pytest.raises(ValueError):
        read_ai_model(p)
    meta = read_ai_model(p, model_format=AiModelFormat.ONNX)
    assert meta.format_info.model_format == AiModelFormat.ONNX


def test_read_ai_model_given_format_still_needs_the_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_ai_model(tmp_path / "gone.onnx", model_format=AiModelFormat.ONNX)
    p = tmp_path / "m.onnx"
    p.write_bytes(b"x")
    with pytest.raises(ValueError):
        read_ai_model(p, model_format=AiModelFormat.UNKNOWN)
