# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Why a file is not read as a model, in the same words and with the same
code on every surface: the reason the header gives, ``read_ai_model()`` and
the single-file commands (``model-wrong-format``, or a Git LFS pointer's).

See also: :mod:`tests.extract.ai_model.test_ai_model_header` (the header
detection these reasons come from).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.assemble import generate_model_sbom
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import not_a_model_reason, read_ai_model
from pitloom.messages import MESSAGES, code_of
from tests._lfs import lfs_pointer_bytes
from tests._message_drift import raised_as

_NOT_A_MODEL = "not an AI model file"  # what a refusal with no reason says
_LOOKS = "header looks like a Git LFS pointer but is not a valid"
_WRONG = "model-wrong-format"
_LFS = b"version https://git-lfs.github.com/spec/v1\noid sha256:00\n"
_GGUF = AiModelFormat.GGUF.magic or b""


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
    ("name", "content", "reason", "code"),
    [
        ("p.bin", _LFS, _LOOKS, "lfs-pointer-malformed"),
        ("p.gguf", _LFS, _LOOKS, "lfs-pointer-malformed"),
        ("t.gguf", b"text", "header is not gguf", _WRONG),
        ("e.onnx", b"", "file is empty", _WRONG),
        ("e.dat", b"", _NOT_A_MODEL, _WRONG),
        ("t.dat", b"text", _NOT_A_MODEL, _WRONG),
    ],
)
def test_read_ai_model_says_why_a_file_is_not_a_model(
    tmp_path: Path, name: str, content: bytes, reason: str, code: str
) -> None:
    """The reason is the one a scan gives; a suffix no reader reads is no
    model of a supported format."""
    f = tmp_path / name
    f.write_bytes(content)
    with pytest.raises(ValueError, match=reason) as exc:
        read_ai_model(f)
    assert code_of(exc.value) == code
    assert str(exc.value).startswith(f"'{f}': ")


@pytest.mark.parametrize(
    ("name", "content", "code"),
    [
        ("e.gguf", b"", _WRONG),
        ("e.onnx", b"", _WRONG),
        ("p.gguf", _LFS, "lfs-pointer-malformed"),
        ("p.bin", _LFS, "lfs-pointer-malformed"),
        ("w.gguf", lfs_pointer_bytes(b"w"), "lfs-pointer"),
        ("t.gguf", b"text", _WRONG),
        ("t.dat", b"text", _WRONG),
    ],
)
def test_a_refused_file_has_the_same_reason_on_every_surface(
    tmp_path: Path, name: str, content: bytes, code: str
) -> None:
    """An empty ``x.gguf`` gets the same reason from ``read_ai_model()`` and
    ``generate_model_sbom``; the reader's reason is the single-file
    command's, and so is its code, a file no reader reads included."""
    f = tmp_path / name
    f.write_bytes(content)
    with pytest.raises(ValueError) as lib:
        read_ai_model(f)
    with pytest.raises(ValueError) as single:
        generate_model_sbom(f)
    assert code_of(lib.value) == code_of(single.value) == code
    assert str(lib.value) == str(single.value)
    assert (_NOT_A_MODEL in str(lib.value)) is (name == "t.dat")
    assert raised_as(lib.value, MESSAGES[code])


@pytest.mark.parametrize("name", ["d.onnx", "d.gguf", "d.h5", "d.dat"])
def test_a_directory_is_refused_as_the_single_file_commands_do(
    tmp_path: Path, name: str
) -> None:
    """A directory named ``d.onnx`` does not run the ONNX reader."""
    (tmp_path / name).mkdir()
    for fmt in (None, AiModelFormat.ONNX):
        with pytest.raises(ValueError, match=_NOT_A_MODEL) as lib:
            read_ai_model(tmp_path / name, model_format=fmt)
        assert code_of(lib.value) == _WRONG
    with pytest.raises(ValueError, match=_NOT_A_MODEL) as single:
        generate_model_sbom(tmp_path / name)
    assert "empty" not in str(single.value)  # a directory is not an empty file
    assert code_of(single.value) == _WRONG
    with pytest.raises(FileNotFoundError):
        read_ai_model(tmp_path / "gone" / name)


def test_read_ai_model_of_an_unreadable_unknown_file_is_no_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reason is looked up in the header; one that cannot be read leaves
    the plain refusal, not a second error."""
    f = tmp_path / "x.dat"
    f.write_bytes(b"x")

    def _deny(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(13, "denied")

    monkeypatch.setattr(Path, "open", _deny)
    with pytest.raises(ValueError, match=_NOT_A_MODEL) as caught:
        read_ai_model(f)
    assert code_of(caught.value) == _WRONG


def test_a_pointer_that_cannot_be_read_again_is_refused_by_its_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``refuse_named_pointer`` returns when the file cannot be read again,
    so there is no ``oid`` to name: the refusal states the reason, uncoded,
    on every surface."""
    f = tmp_path / "w.gguf"
    f.write_bytes(lfs_pointer_bytes(b"w"))

    def _gone(_path: object) -> None:
        raise OSError("gone")

    monkeypatch.setattr("pitloom.core.lfs_pointer.read_lfs_pointer", _gone)
    for read in (read_ai_model, generate_model_sbom):
        with pytest.raises(ValueError) as caught:
            read(f)
        assert str(caught.value) == f"'{f}': header is a Git LFS pointer"
        assert code_of(caught.value) is None
