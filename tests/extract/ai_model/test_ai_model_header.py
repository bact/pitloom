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

from pitloom.assemble import generate_model_sbom
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import (
    SNIFF_BYTES,
    contradicted_format,
    detect_ai_model_format,
    detect_ai_model_format_from_header,
    is_git_lfs_pointer,
    not_a_model_reason,
    read_ai_model,
    read_ai_model_header,
)

_NOT_A_MODEL = "not an AI model file"  # what a refusal with no reason says


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


def _lfs_gguf(tmp: Path) -> Path:
    f = tmp / "lfs.gguf"
    f.write_bytes(_LFS)
    return f


def _text_named(name: str) -> Callable[[Path], Path]:
    def make(tmp: Path) -> Path:
        f = tmp / name
        f.write_text("just some notes", encoding="utf-8")
        return f

    return make


def _empty_ftz(tmp: Path) -> Path:
    f = tmp / "model.ftz"
    f.write_bytes(b"")
    return f


def _text_pth(tmp: Path) -> Path:
    f = tmp / "distutils-precedence.pth"
    f.write_bytes(b"import os; var = 'SETUPTOOLS_USE_DISTUTILS'\n")
    return f


def _empty_pth(tmp: Path) -> Path:
    f = tmp / "empty.pth"
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
        (_fixture("crfsuite/complete.crfsuite"), AiModelFormat.CRFSUITE),
        # the magic decides on the shared `.model` suffix
        (_fixture("crfsuite/minimal.model"), AiModelFormat.CRFSUITE),
        (_text_named("notes.crfsuite"), AiModelFormat.UNKNOWN),
        (_text_named("notes.model"), AiModelFormat.UNKNOWN),
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
        (_empty_ftz, AiModelFormat.UNKNOWN),
        (_lfs_gguf, AiModelFormat.UNKNOWN),
        (_text_pth, AiModelFormat.UNKNOWN),
        (_empty_pth, AiModelFormat.UNKNOWN),
        (_fixture("pytorch/example-model.pth"), AiModelFormat.PYTORCH),
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


@pytest.mark.parametrize("path_factory", [_missing_onnx, _dir_onnx])
def test_path_detection_of_a_non_file_is_by_name_header_detection_is_not(
    tmp_path: Path, path_factory: Callable[[Path], Path]
) -> None:
    """``read_ai_model`` reports absence itself; the header of a file that
    is not there proves nothing."""
    p = path_factory(tmp_path)
    assert detect_ai_model_format(p) == AiModelFormat.ONNX
    assert detect_ai_model_format_from_header(b"", p.name) == AiModelFormat.UNKNOWN


def _st_header(size: int, brace: bytes = b"{") -> bytes:
    return size.to_bytes(8, "little") + brace


_LFS = b"version https://git-lfs.github.com/spec/v1\noid sha256:00\n"
# The spec URLs git-lfs's pointer decoder accepts (current, then the two
# earlier versions).
_LFS_URLS = (
    "https://git-lfs.github.com/spec/v1",
    "https://hawser.github.com/spec/v1",
    "http://git-media.io/v/2",
)
_GGUF, _NPY, _FT, _CRF = (
    _magic(f)
    for f in (
        AiModelFormat.GGUF,
        AiModelFormat.NUMPY,
        AiModelFormat.FASTTEXT,
        AiModelFormat.CRFSUITE,
    )
)


@pytest.mark.parametrize(
    ("header", "name", "expected"),
    [
        # magic beats a disagreeing extension, in both directions
        (_GGUF + b"\0" * 5, "x.npy", AiModelFormat.GGUF),
        (_NPY + b"\0" * 5, "x.bin", AiModelFormat.NUMPY),
        (_FT + b"\0" * 5, "", AiModelFormat.FASTTEXT),
        (_GGUF, "x.onnx", AiModelFormat.GGUF),
        (_CRF + b"\0" * 5, "x.model", AiModelFormat.CRFSUITE),
        (_CRF + b"\0" * 5, "x.bin", AiModelFormat.CRFSUITE),
        (_CRF[:-1], "x.crfsuite", AiModelFormat.UNKNOWN),
        (_CRF[:-1], "x.model", AiModelFormat.UNKNOWN),
        (_LFS, "x.crfsuite", AiModelFormat.UNKNOWN),
        (_LFS, "x.model", AiModelFormat.UNKNOWN),
        # a truncated magic is no magic, and a magic format has no extension
        # fallback (a Git LFS pointer is text): D3
        (_GGUF[:-1], "x.gguf", AiModelFormat.UNKNOWN),
        (_GGUF[:-1], "x.bin", AiModelFormat.UNKNOWN),
        (_NPY[:-1], "x.npy", AiModelFormat.UNKNOWN),
        (_LFS, "x.gguf", AiModelFormat.UNKNOWN),
        (_LFS, "x.ftz", AiModelFormat.UNKNOWN),
        (_LFS, "x.npy", AiModelFormat.UNKNOWN),
        (_LFS, "x.safetensors", AiModelFormat.UNKNOWN),
        # ZIP formats need PK\x03\x04
        (b"PK\x03\x04\0", "x.keras", AiModelFormat.KERAS),
        (b"PK\x03\x04\0", "x.pt2", AiModelFormat.PYTORCH_PT2),
        (b"PK\x03\x04\0", "x.npz", AiModelFormat.NUMPY),
        (_LFS, "x.keras", AiModelFormat.UNKNOWN),
        (_LFS, "x.pt2", AiModelFormat.UNKNOWN),
        (_LFS, "x.npz", AiModelFormat.UNKNOWN),
        # an archive with no member opens with the end-of-central-directory
        # record, not a local header
        (b"PK\x05\x06" + b"\0" * 5, "x.npz", AiModelFormat.NUMPY),
        (b"PK\x05\x06", "x.keras", AiModelFormat.KERAS),
        (b"PK\x05\x06", "x.pt", AiModelFormat.PYTORCH),
        # ONNX and HDF5 have no signature at offset 0: any non-empty header,
        # but never a Git LFS pointer
        (b"\0\x08\x01", "x.onnx", AiModelFormat.ONNX),
        (b"\0\x08\x01", "x.h5", AiModelFormat.HDF5),
        (b"\0\x08\x01", "x.HDF5", AiModelFormat.HDF5),
        (_LFS, "x.onnx", AiModelFormat.UNKNOWN),
        (_LFS, "x.h5", AiModelFormat.UNKNOWN),
        (_LFS, "x.HDF5", AiModelFormat.UNKNOWN),
        (_LFS, "x.pt", AiModelFormat.UNKNOWN),
        (_LFS, "x.pth", AiModelFormat.UNKNOWN),
        # extension: case-insensitive, last suffix only, POSIX names only; an
        # empty header is never a model
        (b"PK\x03\x04", "x.NPZ", AiModelFormat.NUMPY),
        (b"PK\x03\x04", "model.tar.npz", AiModelFormat.NUMPY),
        (b"PK\x03\x04", "model.npz.bak", AiModelFormat.UNKNOWN),
        (b"PK\x03\x04", "d.npz/file", AiModelFormat.UNKNOWN),
        (b"PK\x03\x04", ".npz", AiModelFormat.UNKNOWN),
        (b"x", "my model \u00e9.onnx", AiModelFormat.ONNX),
        (b"", "x.onnx", AiModelFormat.UNKNOWN),
        (b"", "x.h5", AiModelFormat.UNKNOWN),
        (b"", "x.keras", AiModelFormat.UNKNOWN),
        # PyTorch: only a ZIP or a protocol 2..5 pickle; ``.pth`` is also
        # Python path-configuration text. An empty header is no model.
        (b"PK\x03\x04\0\0", "a\\b.pt", AiModelFormat.PYTORCH),
        (b"\x80\x02}q\x00", "x.pth", AiModelFormat.PYTORCH),
        (b"\x80\x05\x95", "x.PT", AiModelFormat.PYTORCH),
        (b"import os;", "distutils-precedence.pth", AiModelFormat.UNKNOWN),
        (b"/opt/lib\n", "x.pt", AiModelFormat.UNKNOWN),
        (b"", "x.pth", AiModelFormat.UNKNOWN),
        (b"\x80", "x.pth", AiModelFormat.UNKNOWN),
        (b"\x80\x01", "x.pth", AiModelFormat.UNKNOWN),
        (b"\x80\x06", "x.pth", AiModelFormat.UNKNOWN),
        (b"PK\x03", "x.pt", AiModelFormat.UNKNOWN),
        (_GGUF, "x.pth", AiModelFormat.GGUF),
        (b"", "x.bin", AiModelFormat.UNKNOWN),
        # Safetensors heuristic: needs all 9 bytes, 0 < size <= the format's
        # limit (safetensors' own, inclusive), then "{"
        (_st_header(19), "x.bin", AiModelFormat.SAFETENSORS),
        (_st_header(100_000_000), "x.bin", AiModelFormat.SAFETENSORS),
        (_st_header(100_000_001), "x.bin", AiModelFormat.UNKNOWN),
        (_st_header(0), "x.bin", AiModelFormat.UNKNOWN),
        (_st_header(19, b"["), "x.bin", AiModelFormat.UNKNOWN),
        (_st_header(19)[:8], "x.bin", AiModelFormat.UNKNOWN),
        (_st_header(19)[:8], "x.safetensors", AiModelFormat.UNKNOWN),
        (_st_header(100_000_001), "x.safetensors", AiModelFormat.UNKNOWN),
    ],
)
def test_detect_from_header(header: bytes, name: str, expected: AiModelFormat) -> None:
    assert detect_ai_model_format_from_header(header, name) == expected


@pytest.mark.parametrize(
    ("header", "name", "expected"),
    [
        (_LFS, "x.gguf", AiModelFormat.GGUF),
        (_LFS, "x.ftz", AiModelFormat.FASTTEXT),
        (_LFS, "x.crfsuite", AiModelFormat.CRFSUITE),
        (b"text, not lCRF", "x.crfsuite", AiModelFormat.CRFSUITE),
        (_CRF, "x.crfsuite", None),
        (_LFS, "x.npy", AiModelFormat.NUMPY),
        (_LFS, "x.keras", AiModelFormat.KERAS),
        (_LFS, "x.NPZ", AiModelFormat.NUMPY),
        (_LFS, "x.pt2", AiModelFormat.PYTORCH_PT2),
        # no suffix excuses a Git LFS pointer, the path-config ones included
        (_LFS, "x.onnx", AiModelFormat.ONNX),
        (_LFS, "x.h5", AiModelFormat.HDF5),
        (_LFS, "x.pt", AiModelFormat.PYTORCH),
        (_LFS, "x.pth", AiModelFormat.PYTORCH),
        (_st_header(100_000_001), "x.safetensors", AiModelFormat.SAFETENSORS),
        (b"GGU", "x.gguf", AiModelFormat.GGUF),
        # a model, or not named by its suffix, or legitimately not a model
        (_GGUF, "x.gguf", None),
        (b"PK\x03\x04", "x.keras", None),
        (b"\0\x08\x01", "x.onnx", None),
        (_LFS, "x.bin", None),
        (b"/opt/lib\n", "x.pth", None),
        (b"/opt/lib\n", "x.pt", None),
        (b"", "x.gguf", None),
        (_GGUF, "x.keras", None),
    ],
)
def test_contradicted_format(
    header: bytes, name: str, expected: AiModelFormat | None
) -> None:
    assert contradicted_format(header, name) == expected


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


@pytest.mark.parametrize("url", _LFS_URLS)
def test_a_git_lfs_pointer_of_every_spec_version_is_no_model(
    tmp_path: Path, url: str
) -> None:
    """Read through the file, so ``SNIFF_BYTES`` must reach the pointer's end
    of ``version <url>``; one byte less is no pointer."""
    version = f"version {url}".encode()
    assert len(version) <= SNIFF_BYTES
    f = tmp_path / "x.onnx"
    f.write_bytes(version + b"\noid sha256:00\nsize 1\n")
    assert is_git_lfs_pointer(read_ai_model_header(f))
    assert detect_ai_model_format(f) == AiModelFormat.UNKNOWN
    assert not is_git_lfs_pointer(version[:-1])
    assert detect_ai_model_format_from_header(version[:-1], "x.onnx") == (
        AiModelFormat.ONNX
    )


@pytest.mark.parametrize(
    ("tail", "is_pointer"),
    [(b"\n", True), (b"\r\n", True), (b"x\n", False), (b" 1\n", False), (b"", False)],
)
@pytest.mark.parametrize("url", _LFS_URLS)
def test_a_git_lfs_version_line_must_be_complete(
    tmp_path: Path, url: str, tail: bytes, is_pointer: bool
) -> None:
    """Regression: a prefix match took ``/spec/v1x`` for a pointer. The sniff
    reaches the end of the longest line, CRLF included."""
    f = tmp_path / "x.onnx"
    f.write_bytes(f"version {url}".encode() + tail + b"oid sha256:00\n")
    assert is_git_lfs_pointer(read_ai_model_header(f)) is is_pointer
    assert (detect_ai_model_format(f) == AiModelFormat.UNKNOWN) is is_pointer


@pytest.mark.parametrize(
    ("header", "name", "reason"),
    [
        (_LFS, "x.gguf", "header is a Git LFS pointer"),
        (_LFS, "x.bin", "header is a Git LFS pointer"),
        (b"text", "x.gguf", "header is not gguf"),
        (b"", "x.gguf", None),
        (b"text", "x.bin", None),
        (_GGUF, "x.gguf", None),
    ],
)
def test_not_a_model_reason(header: bytes, name: str, reason: str | None) -> None:
    assert not_a_model_reason(header, name) == reason


@pytest.mark.parametrize(
    ("name", "content", "reason"),
    [
        ("p.bin", _LFS, "header is a Git LFS pointer"),
        ("p.gguf", _LFS, "header is a Git LFS pointer"),
        ("t.gguf", b"text", "header is not gguf"),
        ("e.onnx", b"", "file is empty"),
        ("e.dat", b"", "Unsupported model format"),
        ("t.dat", b"text", "Unsupported model format"),
    ],
)
def test_read_ai_model_says_why_a_file_is_not_a_model(
    tmp_path: Path, name: str, content: bytes, reason: str
) -> None:
    """The suffix is supported: the reason is the one a scan gives, not a
    claim that the extension is not."""
    f = tmp_path / name
    f.write_bytes(content)
    with pytest.raises(ValueError, match=reason) as exc:
        read_ai_model(f)
    assert ("Supported extensions" in str(exc.value)) is reason.startswith("Unsup")


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("e.gguf", b""),
        ("e.onnx", b""),
        ("p.gguf", _LFS),
        ("p.bin", _LFS),
        ("t.gguf", b"text"),
        ("t.dat", b"text"),
    ],
)
def test_a_refused_file_has_the_same_reason_on_every_surface(
    tmp_path: Path, name: str, content: bytes
) -> None:
    """Regression: an empty ``x.gguf`` was ``file is empty`` to
    ``read_ai_model()`` and ``not an AI model file`` to ``generate_model_sbom``;
    the reader's reason is the single-file command's, when there is one."""
    f = tmp_path / name
    f.write_bytes(content)
    with pytest.raises(ValueError) as lib:
        read_ai_model(f)
    with pytest.raises(ValueError) as single:
        generate_model_sbom(f)
    reason = str(single.value).removeprefix(f"{f}: ")
    if name == "t.dat":  # no reason: each words its own refusal
        assert "Unsupported model format" in str(lib.value)
        assert _NOT_A_MODEL in reason
    else:
        assert str(lib.value) == str(single.value)
        assert _NOT_A_MODEL not in reason


@pytest.mark.parametrize("name", ["d.onnx", "d.gguf", "d.h5", "d.dat"])
def test_a_directory_is_refused_as_the_single_file_commands_do(
    tmp_path: Path, name: str
) -> None:
    """Regression: a directory named ``d.onnx`` ran the ONNX reader."""
    (tmp_path / name).mkdir()
    for fmt in (None, AiModelFormat.ONNX):
        with pytest.raises(ValueError, match=_NOT_A_MODEL):
            read_ai_model(tmp_path / name, model_format=fmt)
    with pytest.raises(ValueError, match=_NOT_A_MODEL) as single:
        generate_model_sbom(tmp_path / name)
    assert "empty" not in str(single.value)  # a directory is not an empty file
    with pytest.raises(FileNotFoundError):
        read_ai_model(tmp_path / "gone" / name)


def test_read_ai_model_of_an_unreadable_unknown_file_names_its_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reason is looked up in the header; one that cannot be read leaves
    the plain "unsupported" message, not a second error."""
    f = tmp_path / "x.dat"
    f.write_bytes(b"x")

    def _deny(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(13, "denied")

    monkeypatch.setattr(Path, "open", _deny)
    with pytest.raises(ValueError, match="Unsupported model format"):
        read_ai_model(f)
