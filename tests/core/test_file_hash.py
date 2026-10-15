# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.file_hash`, the one chunked SHA-256 reader.

See also: tests/core/test_dataset_hash.py (the dataset ceiling built on it).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from pitloom.core import file_hash
from pitloom.core.file_hash import (
    ReadBudgetExceeded,
    sha256_digest,
    sha256_digest_and_size,
)
from pitloom.core.path_confine import NotRegularFileError
from pitloom.id_registry import sha256_file

_CONTENT = bytes(range(256)) * 79  # 20224 bytes: many small chunks


@pytest.mark.parametrize(
    ("max_bytes", "fits"),
    [(None, True), (len(_CONTENT), True), (len(_CONTENT) - 1, False)],
    ids=["no-budget", "exact", "one-over"],
)
def test_digest_streams_in_chunks_within_its_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, max_bytes: int | None, fits: bool
) -> None:
    """Read chunk by chunk, the digest is the whole file's; a budget of
    exactly the size is enough, one byte less fails mid-stream."""
    monkeypatch.setattr(file_hash, "CHUNK_BYTES", 1000)
    path = tmp_path / "data.bin"
    path.write_bytes(_CONTENT)
    if not fits:
        with pytest.raises(ReadBudgetExceeded, match=f"read more than {max_bytes}"):
            sha256_digest(path, max_bytes=max_bytes)
        return
    expected = hashlib.sha256(_CONTENT).digest()
    assert sha256_digest_and_size(path, max_bytes=max_bytes) == (
        expected,
        len(_CONTENT),
    )
    assert sha256_file(path) == expected.hex()  # the registry's hex form


def test_digest_refuses_a_directory(tmp_path: Path) -> None:
    """Not a regular file once open: an ``OSError``, never a digest."""
    with pytest.raises(OSError):
        sha256_digest(tmp_path)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs a FIFO")
def test_digest_refuses_a_fifo_without_blocking(tmp_path: Path) -> None:
    """A FIFO (no writer) opens at once and is refused, not waited on."""
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)  # pylint: disable=no-member
    with pytest.raises(NotRegularFileError):
        sha256_digest(fifo)
