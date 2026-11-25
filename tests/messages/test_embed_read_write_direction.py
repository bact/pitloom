# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An embed's I/O error said by its direction: a read of the source wheel's
member is ``file-unreadable`` ("could not read"), a write of the new wheel
``file-unwritable`` ("could not write"), both naming the wheel by its file
name; either way no temporary file is left and the wheel is as it was.
Standard output (``-o -``) is never called a file named ``-``.

See also: tests/messages/test_file_unwritable_embed.py (the refused writes
on every surface).
"""

from __future__ import annotations

import errno
import io
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom import _embed_wheel, _sbom_io
from pitloom._wheel_sbom_location import read_wheel_member
from pitloom.assemble import embed_sbom_in_wheel
from pitloom.core import wheel_dist_info
from pitloom.messages import CodedOSError, code_of
from pitloom.messages.files import SBOM_USE, file_unwritable_error
from tests.assemble.conftest import _make_dummy_wheel

pytestmark = pytest.mark.platform

_WHEEL = "demo-1.0.0-py3-none-any.whl"
_SBOM = '{"@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld"}'
_EIO = "Input/output error"


def _eio(*_: object, **__: object) -> bytes:
    raise OSError(errno.EIO, _EIO)


class _FailingStream(io.BytesIO):
    """A member stream whose every read is an I/O error."""

    def read(self, _size: int | None = -1, /) -> bytes:
        return _eio()


def _real_reader_over_failing_stream(
    _source: object, archive: str, entry: str
) -> wheel_dist_info.RefusingReader:
    return wheel_dist_info.RefusingReader(_FailingStream(), archive, entry)


def _embed_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, patch: Callable[[], None]
) -> tuple[OSError, Path, bytes]:
    wheel = _make_dummy_wheel(tmp_path, "demo", "1.0.0")
    before = wheel.read_bytes()
    patch()
    with pytest.raises(OSError) as caught:
        embed_sbom_in_wheel(wheel, _SBOM)
    monkeypatch.undo()
    return caught.value, wheel, before


@pytest.mark.parametrize(
    ("direction", "code", "verb"),
    [
        ("member-read", "file-unreadable", "read"),
        ("archive-write", "file-unwritable", "write"),
        ("replace", "file-unwritable", "write"),
    ],
    ids=["member-read", "archive-write", "replace"],
)
def test_an_io_error_is_said_by_its_direction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    direction: str,
    code: str,
    verb: str,
) -> None:
    def patch() -> None:
        if direction == "member-read":
            monkeypatch.setattr(
                _embed_wheel, "RefusingReader", _real_reader_over_failing_stream
            )
        elif direction == "archive-write":
            monkeypatch.setattr("zipfile._ZipWriteFile.write", _eio)
        else:
            monkeypatch.setattr("os.replace", _eio)

    exc, wheel, before = _embed_failing(tmp_path, monkeypatch, patch)
    assert isinstance(exc, CodedOSError)
    assert str(exc) == f"FILE={_WHEEL}: could not {verb} for the SBOM; {_EIO}"
    assert code_of(exc) == code
    assert wheel.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == [_WHEEL]


@pytest.mark.parametrize(
    ("error", "code", "text"),
    [
        (
            OSError(errno.EIO, _EIO),
            "file-unreadable",
            f"could not read for the SBOM; {_EIO}",
        ),
        (
            FileNotFoundError(errno.ENOENT, "No such file or directory"),
            "input-not-found",
            "wheel file not found",
        ),
    ],
    ids=["io-error", "gone"],
)
def test_every_member_read_says_a_system_error_coded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: OSError,
    code: str,
    text: str,
) -> None:
    """The shared member reader (``verify-wheel``, ``validate-wheel``,
    reading ``METADATA``): an ``OSError`` still, now coded."""
    wheel = _make_dummy_wheel(tmp_path, "demo", "1.0.0")
    with zipfile.ZipFile(wheel) as zf:
        info = zf.infolist()[0]

        def fail(*_: object, **__: object) -> bytes:
            raise error

        monkeypatch.setattr(zf, "read", fail)
        with pytest.raises(OSError) as caught:
            read_wheel_member(zf, info)
    assert code_of(caught.value) == code
    assert text in str(caught.value)
    assert str(tmp_path) not in str(caught.value)


def test_a_coded_os_error_in_a_member_read_passes_as_it_is() -> None:
    coded = file_unwritable_error(OSError(errno.EIO, _EIO), file="x", use=SBOM_USE)
    with pytest.raises(OSError) as caught:
        with wheel_dist_info.refuse_unreadable(_WHEEL, "x"):
            raise coded
    assert caught.value is coded


def test_standard_output_is_written_there(capsys: pytest.CaptureFixture[str]) -> None:
    _sbom_io.write_sbom_output(_SBOM, "-")
    assert capsys.readouterr().out == _SBOM + "\n"


def test_a_closed_standard_output_is_not_a_file_named_dash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``-o - | (exec 0<&-; true)``: the pipe's error as every command
    meets it, never ``FILE=-: could not write``."""

    def broken(_text: str) -> None:
        raise BrokenPipeError(errno.EPIPE, "Broken pipe")

    monkeypatch.setattr(_sbom_io, "write_stdout_lf", broken)
    with pytest.raises(BrokenPipeError) as caught:
        _sbom_io.write_sbom_output(_SBOM, "-")
    assert code_of(caught.value) is None
    assert "FILE=-" not in str(caught.value)
