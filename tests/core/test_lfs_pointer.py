# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.lfs_pointer`: the pointer grammar, its
bounded reads, and a drift guard against ``git lfs pointer --check``.

See also: tests/fixtures/lfs-pointers/README.md (the real pointers);
tests/extract/ai_model/test_ai_model_header.py (the model gate).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from pitloom.core import lfs_pointer
from pitloom.core.lfs_pointer import (
    LFS_OPENING_BYTES,
    LFS_POINTER_MAX_BYTES,
    LfsPointer,
    PrefixCapture,
    opens_lfs_pointer,
    parse_lfs_pointer,
    read_lfs_pointer,
)
from tests._lfs import lfs_pointer_bytes, pointer_fixture

_CONTENT = b"hello"
_HEX = hashlib.sha256(_CONTENT).hexdigest()
_HELLO = LfsPointer(_HEX, 5)
_HELLO_BYTES = lfs_pointer_bytes(_CONTENT)
_VERSION = "version https://git-lfs.github.com/spec/v1"
_EXT = f"ext-0-foo sha256:{_HEX}"


def _text(*lines: str, eol: str = "\n", end: bool = True) -> bytes:
    return (eol.join(lines) + (eol if end else "")).encode()


def _hello(*, size: str = "5", oid: str = _HEX, version: str = _VERSION) -> bytes:
    return _text(version, f"oid sha256:{oid}", f"size {size}")


def _padded(total: int) -> bytes:
    """The hello pointer, an extension name stretched to *total* bytes."""
    name = "x" * (total - len(_hello()) - len(f"ext-0- sha256:{_HEX}\n"))
    return _text(
        _VERSION, f"ext-0-{name} sha256:{_HEX}", f"oid sha256:{_HEX}", "size 5"
    )


_MAX = 2**63 - 1
# id -> (bytes, our verdict); git-lfs 3.4.1 must agree except in _STRICTER.
_MATRIX: dict[str, tuple[bytes, LfsPointer | None]] = {
    "canonical": (_HELLO_BYTES, _HELLO),
    "hawser": (
        lfs_pointer_bytes(_CONTENT, url="https://hawser.github.com/spec/v1"),
        _HELLO,
    ),
    "git-media": (lfs_pointer_bytes(_CONTENT, url="http://git-media.io/v/2"), _HELLO),
    "crlf": (lfs_pointer_bytes(_CONTENT, eol="\r\n"), _HELLO),
    "no-final-eol": (lfs_pointer_bytes(_CONTENT, trailing_newline=False), _HELLO),
    "crlf-no-final": (
        lfs_pointer_bytes(_CONTENT, eol="\r\n", trailing_newline=False),
        _HELLO,
    ),
    "ext": (_text(_VERSION, _EXT, f"oid sha256:{_HEX}", "size 5"), _HELLO),
    "ext-two-crlf": (
        _text(
            _VERSION,
            _EXT,
            _EXT[:4] + "1" + _EXT[5:],
            f"oid sha256:{_HEX}",
            "size 5",
            eol="\r\n",
        ),
        _HELLO,
    ),
    "size-0": (lfs_pointer_bytes(b""), LfsPointer(hashlib.sha256().hexdigest(), 0)),
    "size-max": (_hello(size=str(_MAX)), LfsPointer(_HEX, _MAX)),
    "1023-bytes": (_padded(1023), _HELLO),
    "1024-bytes": (_padded(1024), None),
    "hex-63": (_hello(oid=_HEX[:63]), None),
    "hex-65": (_hello(oid=_HEX + "0"), None),
    "hex-upper": (_hello(oid=_HEX.upper()), None),
    "sha1": (_text(_VERSION, f"oid sha1:{_HEX[:40]}", "size 5"), None),
    "size-first": (_text(_VERSION, "size 5", f"oid sha256:{_HEX}"), None),
    "no-size": (_text(_VERSION, f"oid sha256:{_HEX}"), None),
    "extra-key": (_hello() + b"foo bar\n", None),
    "ext-after-oid": (_text(_VERSION, f"oid sha256:{_HEX}", _EXT, "size 5"), None),
    "blank-line": (_text(_VERSION, "", f"oid sha256:{_HEX}", "size 5"), None),
    "trailing-blank": (_hello() + b"\n", None),
    "trailing-space": (_hello(size="5 "), None),
    "size-plus": (_hello(size="+5"), None),
    "size-underscore": (_hello(size="1_0"), None),
    "size-arabic": (_hello(size="\u0665"), None),
    "size-negative": (_hello(size="-5"), None),
    "size-leading-0": (_hello(size="05"), None),
    "size-2**63": (_hello(size=str(_MAX + 1)), None),
    "bom": (b"\xef\xbb\xbf" + lfs_pointer_bytes(_CONTENT), None),
    "v1x": (_hello(version=_VERSION + "x"), None),
    "https-git-media": (_hello(version="version https://git-media.io/v/2"), None),
    "cr-only": (lfs_pointer_bytes(_CONTENT, eol="\r"), None),
    "mixed-eol": (
        _VERSION.encode() + b"\r\n" + _text(f"oid sha256:{_HEX}", "size 5", end=False),
        None,
    ),
    "mixed-final-eol": (lfs_pointer_bytes(_CONTENT, eol="\r\n")[:-2] + b"\n", None),
    "empty": (b"", None),
    "binary": (_VERSION.encode() + b"\n\x00\xff\xfe\x01" * 8, None),
}

#: Rows git-lfs's non-strict decoder accepts (``--strict`` exits 2 on all but
#: two) that this grammar refuses: oddities git-lfs never writes, a 1024-byte
#: pointer (the cut-off here), the empty file (the pointer of empty content
#: there, never one here).
_STRICTER = frozenset(
    {
        "1024-bytes",
        "ext-after-oid",
        "blank-line",
        "trailing-blank",
        "trailing-space",
        "size-plus",
        "size-leading-0",
        "mixed-eol",
        "mixed-final-eol",
        "empty",
    }
)


@pytest.mark.parametrize(
    ("data", "opens"),
    [
        (_HELLO_BYTES, True),
        (lfs_pointer_bytes(eol="\r\n"), True),
        (lfs_pointer_bytes(url="https://hawser.github.com/spec/v1", eol="\r\n"), True),
        (lfs_pointer_bytes(url="http://git-media.io/v/2"), True),
        (_hello(version=_VERSION + "x"), False),
        (_VERSION.encode(), False),
        (lfs_pointer_bytes(eol="\r"), False),
        (b"\xef\xbb\xbf" + _HELLO_BYTES, False),
    ],
    ids=["lf", "crlf", "hawser-crlf", "git-media", "v1x", "no-eol", "cr", "bom"],
)
def test_opens_lfs_pointer(data: bytes, opens: bool) -> None:
    """The whole version line, its ending included, within the first
    :data:`LFS_OPENING_BYTES` bytes."""
    assert opens_lfs_pointer(data[:LFS_OPENING_BYTES]) is opens


@pytest.mark.parametrize(("data", "expected"), _MATRIX.values(), ids=_MATRIX)
def test_pointer_grammar(data: bytes, expected: LfsPointer | None) -> None:
    """The whole-data verdict; every pointer opens with its version line;
    a prefix capture fed in chunks of any size agrees with it."""
    assert parse_lfs_pointer(data) == expected
    if expected is not None:
        assert opens_lfs_pointer(data[:LFS_OPENING_BYTES])
    for size in (1, 7, 64):
        capture = PrefixCapture()
        for start in range(0, len(data), size):
            capture.feed(data[start : start + size])
        assert capture.pointer() == expected


@pytest.mark.parametrize(
    ("name", "size"),
    [
        ("aa-lcr-extracted-text.zip", 4023468),
        ("aime-2024-problems.parquet", 37189),
        ("bert-tiny-pytorch-model.bin", 17756393),
        ("humaneval-test.parquet", 83920),
        ("static-js-app-main.js", 28),
    ],
)
def test_real_pointers_parse(name: str, size: int) -> None:
    pointer = read_lfs_pointer(pointer_fixture(name))
    assert pointer is not None and len(pointer.oid) == 64
    assert pointer.size == size


def test_prefix_capture_stays_bounded() -> None:
    """A pointer followed by 10 MB is content; at most the cut-off is held."""
    capture = PrefixCapture()
    capture.feed(_HELLO_BYTES)
    for _ in range(10):
        capture.feed(b"\0" * 1_000_000)
        assert capture.retained <= LFS_POINTER_MAX_BYTES
    assert capture.pointer() is None


@pytest.fixture(name="reads")
def _reads(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int]]:
    """``(asked, got)`` bytes per read of a file the module opens."""
    reads: list[tuple[int, int]] = []

    def spy_open(*args: Any, **kwargs: Any) -> Any:
        # pylint: disable-next=consider-using-with,unspecified-encoding
        handle: Any = open(*args, **kwargs)
        real_read = handle.read

        def read(size: int = -1) -> Any:
            chunk = real_read(size)
            reads.append((size, len(chunk or b"")))
            return chunk

        handle.read = read
        return handle

    monkeypatch.setattr(lfs_pointer, "open", spy_open, raising=False)
    return reads


_SPARSE = 64 * 1024 * 1024


@pytest.mark.parametrize(
    ("data", "size", "expected", "most"),
    [
        (_HELLO_BYTES, 0, _HELLO, len(_HELLO_BYTES)),
        (_padded(1023), 0, _HELLO, 1023),
        (_padded(1024), 0, None, 0),
        (_HELLO_BYTES, _SPARSE, None, 0),
    ],
    ids=["pointer", "1023", "1024", "sparse-64MiB"],
)
def test_read_lfs_pointer_reads_at_most_the_cut_off(
    tmp_path: Path,
    reads: list[tuple[int, int]],
    data: bytes,
    size: int,
    expected: LfsPointer | None,
    most: int,
) -> None:
    """Never more than the cut-off is asked for, and a file the size of
    which rules a pointer out (a sparse one opening with a pointer
    included) is not read at all."""
    path = tmp_path / "f"
    path.write_bytes(data)
    if size:
        with path.open("r+b") as handle:
            handle.truncate(size)
    assert read_lfs_pointer(path) == expected
    assert sum(got for _, got in reads) == most
    assert all(0 <= asked <= LFS_POINTER_MAX_BYTES for asked, _ in reads)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no named pipes")
def test_read_lfs_pointer_refuses_a_named_pipe_holding_a_pointer(
    tmp_path: Path,
) -> None:
    """A FIFO is not a regular file: refused once open, even when a writer
    has already put a whole pointer in it (the open never waits for one)."""
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    # O_RDWR opens a FIFO without blocking and keeps the data readable.
    held = os.open(fifo, os.O_RDWR)
    try:
        os.write(held, _HELLO_BYTES)
        assert read_lfs_pointer(fifo) is None
    finally:
        os.close(held)


@pytest.mark.parametrize(
    ("size", "limit", "wanted"),
    [(10, LFS_POINTER_MAX_BYTES, 10), (3000, LFS_POINTER_MAX_BYTES, 1024)],
    ids=["shorter-than-the-limit", "longer-than-the-limit"],
)
def test_read_at_most_stops_at_the_end_or_at_the_limit(
    tmp_path: Path, size: int, limit: int, wanted: int
) -> None:
    """A file shorter than its stated size ends the loop at the empty read;
    a longer one at the limit."""
    path = tmp_path / "f"
    path.write_bytes(b"x" * size)
    with path.open("rb", buffering=0) as handle:
        # pylint: disable-next=protected-access
        assert len(lfs_pointer._read_at_most(handle, limit)) == wanted


def test_read_lfs_pointer_raises_when_it_cannot_open(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        read_lfs_pointer(tmp_path / "gone")
    with pytest.raises(OSError):
        read_lfs_pointer(tmp_path)


@pytest.fixture(name="git_lfs", scope="module")
def _git_lfs() -> str:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is not installed")
    probe = subprocess.run([git, "lfs", "version"], capture_output=True, check=False)
    if probe.returncode != 0:
        pytest.skip("git-lfs is not installed")
    return git


@pytest.mark.parametrize("row", _MATRIX)
def test_git_lfs_agrees_with_the_grammar(
    git_lfs: str, tmp_path: Path, row: str
) -> None:
    """Accepted here implies accepted by git-lfs; refused here is refused
    there too, except the rows in ``_STRICTER``, which git-lfs accepts."""
    checked = subprocess.run(
        [git_lfs, "lfs", "pointer", "--check", "--stdin"],
        input=_MATRIX[row][0],
        capture_output=True,
        check=False,
        cwd=tmp_path,
    )
    accepted = _MATRIX[row][1] is not None or row in _STRICTER
    assert (checked.returncode == 0) is accepted
