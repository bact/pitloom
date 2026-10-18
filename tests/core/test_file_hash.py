# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.file_hash`, the one chunked reader (SHA-256
alone, or SHA-256 and SHA-512 in one pass).

See also: tests/core/test_dataset_hash.py (the dataset ceiling built on it).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from pitloom.core import file_hash
from pitloom.core.file_hash import (
    DigestHasher,
    FileDigests,
    HexDigests,
    ReadBudgetExceeded,
    file_digests,
    sha256_digest,
    sha256_digest_and_size,
)
from pitloom.core.path_confine import NotRegularFileError
from pitloom.id_registry import sha256_file

_CONTENT = bytes(range(256)) * 79  # 20224 bytes: many small chunks
_CHUNK = 1000

#: Both readers, so each refusal below is proved for each.
_READERS = {"sha256": sha256_digest, "both": file_digests}


def _expected(content: bytes) -> FileDigests:
    return FileDigests(
        hashlib.sha256(content).digest(),
        hashlib.sha512(content).digest(),
        len(content),
    )


@pytest.mark.parametrize(
    ("max_bytes", "fits"),
    [(None, True), (len(_CONTENT), True), (len(_CONTENT) - 1, False)],
    ids=["no-budget", "exact", "one-over"],
)
def test_digest_streams_in_chunks_within_its_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, max_bytes: int | None, fits: bool
) -> None:
    """Read chunk by chunk, the digest is the whole file's; a budget of
    exactly the size is enough, one byte less fails mid-stream, for the
    SHA-256 reader and the two-digest one alike."""
    monkeypatch.setattr(file_hash, "CHUNK_BYTES", _CHUNK)
    path = tmp_path / "data.bin"
    path.write_bytes(_CONTENT)
    if not fits:
        for reader in _READERS.values():
            with pytest.raises(ReadBudgetExceeded, match=f"read more than {max_bytes}"):
                reader(path, max_bytes=max_bytes)
        return
    expected = _expected(_CONTENT)
    assert sha256_digest_and_size(path, max_bytes=max_bytes) == (
        expected.sha256,
        len(_CONTENT),
    )
    assert sha256_file(path) == expected.sha256.hex()  # the registry's hex form
    assert file_digests(path, max_bytes=max_bytes) == expected


@pytest.mark.parametrize(
    "size",
    [0, 1, _CHUNK - 1, _CHUNK, _CHUNK + 1, 3 * _CHUNK],
    ids=["empty", "one", "chunk-1", "chunk", "chunk+1", "three-chunks"],
)
def test_both_digests_match_hashlib_at_every_chunk_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, size: int
) -> None:
    """One pass gives :mod:`hashlib`'s SHA-256 and SHA-512 of the whole
    file, the empty file included, and the hasher fed the same bytes in
    other slices agrees (drift guard: the archive readers feed it)."""
    monkeypatch.setattr(file_hash, "CHUNK_BYTES", _CHUNK)
    content = (_CONTENT * 2)[:size]
    path = tmp_path / "data.bin"
    path.write_bytes(content)
    found = file_digests(path)
    assert found == _expected(content)
    assert found.hex() == HexDigests(
        hashlib.sha256(content).hexdigest(), hashlib.sha512(content).hexdigest()
    )
    hasher = DigestHasher()
    for start in range(0, size, 7):
        hasher.update(content[start : start + 7])
    assert hasher.digests() == found


@pytest.mark.parametrize("reader", _READERS)
def test_digest_refuses_a_directory(tmp_path: Path, reader: str) -> None:
    """Not a regular file once open: an ``OSError``, never a digest."""
    with pytest.raises(OSError):
        _READERS[reader](tmp_path)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs a FIFO")
@pytest.mark.parametrize("reader", _READERS)
def test_digest_refuses_a_fifo_without_blocking(tmp_path: Path, reader: str) -> None:
    """A FIFO (no writer) opens at once and is refused, not waited on."""
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)  # pylint: disable=no-member
    with pytest.raises(NotRegularFileError):
        _READERS[reader](fifo)


def test_the_sha256_reader_computes_no_sha512(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hash that only keys or gates something pays for no SHA-512: it
    never builds the two-digest hasher, which the SBOM reader does (so the
    refusal is seen)."""
    path = tmp_path / "data.bin"
    path.write_bytes(_CONTENT)

    def _refused() -> DigestHasher:
        raise RuntimeError("two-digest hasher built")

    monkeypatch.setattr(file_hash, "DigestHasher", _refused)
    assert sha256_digest_and_size(path)[1] == len(_CONTENT)
    with pytest.raises(RuntimeError, match="two-digest hasher built"):
        file_digests(path)
