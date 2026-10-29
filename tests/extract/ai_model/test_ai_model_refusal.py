# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Why a file is not read as a model, in the same words on every surface:
the reason the header gives, ``read_ai_model()`` and the single-file
commands, the catalogued code of a Git LFS pointer included.

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
from pitloom.messages import code_of
from tests._lfs import lfs_pointer_bytes

_NOT_A_MODEL = "not an AI model file"  # what a refusal with no reason says
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
    ("name", "content", "reason"),
    [
        ("p.bin", _LFS, "header looks like a Git LFS pointer but is not a valid"),
        ("p.gguf", _LFS, "header looks like a Git LFS pointer but is not a valid"),
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
    ("name", "content", "code"),
    [
        ("e.gguf", b"", None),
        ("e.onnx", b"", None),
        ("p.gguf", _LFS, "lfs-pointer-malformed"),
        ("p.bin", _LFS, "lfs-pointer-malformed"),
        ("w.gguf", lfs_pointer_bytes(b"w"), "lfs-pointer"),
        ("t.gguf", b"text", None),
        ("t.dat", b"text", None),
    ],
)
def test_a_refused_file_has_the_same_reason_on_every_surface(
    tmp_path: Path, name: str, content: bytes, code: str | None
) -> None:
    """An empty ``x.gguf`` gets the same reason from ``read_ai_model()`` and
    ``generate_model_sbom``; the reader's reason is the single-file
    command's, and so is the catalogued code of a Git LFS pointer."""
    f = tmp_path / name
    f.write_bytes(content)
    with pytest.raises(ValueError) as lib:
        read_ai_model(f)
    with pytest.raises(ValueError) as single:
        generate_model_sbom(f)
    reason = str(single.value).removeprefix(f"{f}: ")
    assert code_of(lib.value) == code_of(single.value) == code
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
    """A directory named ``d.onnx`` does not run the ONNX reader."""
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
