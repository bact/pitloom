# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Git LFS pointers in :mod:`pitloom.core.dataset_hash`: a
pointer stands in by its ``oid``, so a file's hash and a directory's root
are the same after ``git lfs pull``; the ceiling still compares the bytes
on disk, never the stated size.

See also: tests/core/test_dataset_hash.py (hashing at large),
tests/core/test_loom_lfs_pointer.py (what loom records of it).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.core.dataset_hash import DatasetDigest, hash_dataset
from pitloom.core.lfs_pointer import LFS_POINTER_MAX_BYTES, parse_lfs_pointer
from tests._lfs import lfs_pointer_bytes, pointer_fixture

_BIG = 1 << 40
_OPENING = b"version https://git-lfs.github.com/spec/v1\n"
#: A pointer stating 2**40 bytes of content that is not at hand.
_HUGE = _OPENING + b"oid sha256:" + b"ab" * 32 + b"\nsize 1099511627776\n"


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


def _tree(top: Path, files: dict[str, bytes]) -> Path:
    for name, data in files.items():
        (top / name).parent.mkdir(parents=True, exist_ok=True)
        (top / name).write_bytes(data)
    return top


@pytest.mark.parametrize("sha512", [False, True])
@pytest.mark.parametrize(
    "make",
    [
        lambda: lfs_pointer_bytes(b"content"),
        lambda: lfs_pointer_bytes(b"crlf", eol="\r\n"),
        lambda: lfs_pointer_bytes(
            b"old", url="http://git-media.io/v/2", trailing_newline=False
        ),
        lambda: pointer_fixture("humaneval-test.parquet").read_bytes(),
    ],
    ids=["lf", "crlf", "git-media-no-eol", "hub"],
)
def test_a_pointer_file_hashes_to_its_oid(
    tmp_path: Path, make: Callable[[], bytes], sha512: bool
) -> None:
    """The oid is the file's SHA-256, with no SHA-512 (content not read)."""
    data = make()
    path = _tree(tmp_path, {"p.parquet": data}) / "p.parquet"
    pointer = parse_lfs_pointer(data)
    assert pointer is not None
    assert hash_dataset(path, max_bytes=_BIG, sha512=sha512) == DatasetDigest(
        "file", pointer.oid, 1, lfs_pointers=((str(path), pointer),), size=None
    )


@pytest.mark.parametrize("sha512", [False, True])
def test_the_hash_is_the_same_after_a_pull(tmp_path: Path, sha512: bool) -> None:
    """A file's hash and a directory's root over pointers and other files
    equal the ones over the pulled content, and repeat bit for bit."""
    content = {"a/x.parquet": b"x" * 3000, "b.bin": b"\x00\x01", "c.txt": b"c\n"}
    pointers = {name: lfs_pointer_bytes(data) for name, data in content.items()}
    pointers["c.txt"] = content["c.txt"]  # an ordinary file among them
    checkout = _tree(tmp_path / "checkout", pointers)
    pulled = _tree(tmp_path / "pulled", content)
    assert (checkout / "a/x.parquet").read_bytes() != content["a/x.parquet"]
    before = hash_dataset(checkout, max_bytes=_BIG)
    after = hash_dataset(pulled, max_bytes=_BIG)
    assert before == hash_dataset(checkout, max_bytes=_BIG)
    assert (before.hex_digest, before.file_count) == (after.hex_digest, 3)
    assert before.hex_digest is not None
    assert [p for p, _ in before.lfs_pointers] == [
        str(checkout / "a/x.parquet"),
        str(checkout / "b.bin"),
    ]
    assert not after.lfs_pointers
    one = hash_dataset(checkout / "b.bin", max_bytes=_BIG, sha512=sha512)
    pulled_one = hash_dataset(pulled / "b.bin", max_bytes=_BIG, sha512=sha512)
    assert one.hex_digest == pulled_one.hex_digest
    assert (pulled_one.hex_sha512 is not None) is sha512
    assert one.hex_sha512 is None


@pytest.mark.parametrize("kind", ["file", "dir"])
@pytest.mark.parametrize("over", [0, 1], ids=["at-ceiling", "one-over"])
def test_the_ceiling_compares_bytes_on_disk_not_the_stated_size(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, kind: str, over: int
) -> None:
    """A pointer stating 2**40 bytes is hashed, silently, under a ceiling of
    the bytes on disk (in a directory, with a file read after it); one byte
    less and it is over, as any file is."""
    pointer = parse_lfs_pointer(_HUGE)
    assert pointer is not None
    top = _tree(tmp_path / "d", {"huge.bin": _HUGE, "z.txt": b"z"})
    path = top if kind == "dir" else top / "huge.bin"
    total = len(_HUGE) + (1 if kind == "dir" else 0)
    assert pointer.size > total
    with caplog.at_level(logging.WARNING):
        found = hash_dataset(path, max_bytes=total - over)
    hashed = ((str(top / "huge.bin"), pointer),)
    assert found.lfs_pointers == (() if over else hashed)
    assert (found.hex_digest is None) is bool(over)
    warnings = _warnings(caplog)
    assert len(warnings) == over
    assert all("max-dataset-hash-bytes cap" in w for w in warnings)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        _OPENING + b"x" * (LFS_POINTER_MAX_BYTES - len(_OPENING)),
        _OPENING + b"oid sha256:" + b"a" * 63 + b"\nsize 5\n",
        lfs_pointer_bytes(b"content", eol="\r\n").replace(b"\r\n", b"\n", 1),
    ],
    ids=["empty", "opens-like-one-1KiB", "oid-63-hex", "mixed-eol"],
)
@pytest.mark.parametrize("kind", ["file", "dir"])
def test_what_is_not_a_pointer_hashes_as_its_bytes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, data: bytes, kind: str
) -> None:
    """Its own SHA-256 (and leaf), no pointer, and the ceiling as ever."""
    assert parse_lfs_pointer(data) is None
    top = _tree(tmp_path / "d", {"f.bin": data})
    path = top if kind == "dir" else top / "f.bin"
    found = hash_dataset(path, max_bytes=_BIG)
    own = hashlib.sha256(data).digest()
    leaf = hashlib.sha256(b"f.bin\x00" + own).hexdigest()
    assert found.hex_digest == (leaf if kind == "dir" else own.hex())
    assert not found.lfs_pointers
    if data:
        with caplog.at_level(logging.WARNING):
            assert hash_dataset(path, max_bytes=len(data) - 1).hex_digest is None
        assert len(_warnings(caplog)) == 1
