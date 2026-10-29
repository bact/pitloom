# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the *size* and *omitted* of a
:class:`~pitloom.core.dataset_hash.DatasetDigest`: a file's measured size,
the ``stat()`` size when the ceiling forbids the read, never a Git LFS
pointer's own size, and ``"over-cap"`` only for the ceiling.

See also: tests/core/test_dataset_hash.py (hashing at large),
tests/core/test_dataset_hash_lfs.py (Git LFS pointers).
"""

from __future__ import annotations

import errno
import hashlib
import logging
import os
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from pitloom.core import dataset_hash
from pitloom.core.evidence import REASON_CODES
from pitloom.core.file_hash import sha256_read
from pitloom.core.lfs_pointer import LFS_POINTER_MAX_BYTES, parse_lfs_pointer
from tests._lfs import lfs_pointer_bytes

_BIG = 1 << 40
#: Over a pointer's size, so a ``stat()`` size of it is the content's.
_DATA = bytes(range(256)) * 8
_POINTER = lfs_pointer_bytes(_DATA)
_PAST = LFS_POINTER_MAX_BYTES - 1  # the largest size a pointer can have
#: The ``stat()`` size a grown file had before it grew.
_STAT = 1500


class _Row(NamedTuple):
    """A dataset ``d/`` holding ``f.bin`` of *data*: the file, or with
    *as_dir* the directory, hashed within *max_bytes*; *fault* patches the
    reader or ``stat()``."""

    data: bytes
    max_bytes: int
    as_dir: bool = False
    fault: str = ""
    sha512: bool = False


#: A row, and the (kind, hashed, size, omitted) it gives.
_ROWS: dict[str, tuple[_Row, tuple[str, bool, int | None, str | None]]] = {
    "file-under-cap": (_Row(_DATA, _BIG), ("file", True, len(_DATA), None)),
    "file-under-cap-sha512": (
        _Row(_DATA, _BIG, sha512=True),
        ("file", True, len(_DATA), None),
    ),
    "pointer-under-cap": (_Row(_POINTER, _BIG), ("file", True, None, None)),
    "file-over-at-stat": (
        _Row(_DATA, len(_DATA) - 1, fault="no-read"),
        ("file", False, len(_DATA), "over-cap"),
    ),
    "file-over-at-pointer-max": (
        _Row(_DATA[: _PAST + 1], _PAST, fault="no-read"),
        ("file", False, _PAST + 1, "over-cap"),
    ),
    "file-over-below-pointer-max": (
        _Row(_DATA[:_PAST], _PAST - 1, fault="no-read"),
        ("file", False, None, "over-cap"),
    ),
    "file-grown-during-read": (
        _Row(_DATA, _STAT, fault="stat-small"),
        ("file", False, _STAT, "over-cap"),
    ),
    "file-unreadable": (_Row(_DATA, _BIG, fault="deny"), ("file", False, None, None)),
    "dir-hashed": (_Row(_DATA, _BIG, as_dir=True), ("dir", True, None, None)),
    "dir-over-at-stat": (
        _Row(_DATA, len(_DATA) - 1, as_dir=True, fault="no-read"),
        ("dir", False, None, "over-cap"),
    ),
    "dir-grown-during-read": (
        _Row(_DATA, len(_DATA), as_dir=True, fault="grow"),
        ("dir", False, None, "over-cap"),
    ),
    "dir-unreadable-leaf": (
        _Row(_DATA, _BIG, as_dir=True, fault="deny"),
        ("dir", False, None, None),
    ),
}


def _no_read(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("nothing over the ceiling is opened")


def _grow_then_read(member: str, **kwargs: Any) -> Any:
    with open(member, "ab") as grown:
        grown.write(b"+")
    return sha256_read(member, **kwargs)


def _denied(member: str, **_kwargs: Any) -> Any:
    raise PermissionError(errno.EACCES, "Permission denied", member)


def _inject(monkeypatch: pytest.MonkeyPatch, fault: str) -> None:
    if fault == "stat-small":
        monkeypatch.setattr(dataset_hash, "_file_size", lambda _path: _STAT)
    readers = {"no-read": _no_read, "grow": _grow_then_read, "deny": _denied}
    if fault in readers:
        monkeypatch.setattr(dataset_hash, "sha256_read", readers[fault])
        monkeypatch.setattr(dataset_hash, "file_digests", readers[fault])


@pytest.mark.parametrize(("row", "expected"), _ROWS.values(), ids=_ROWS.keys())
def test_size_and_omitted_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    row: _Row,
    expected: tuple[str, bool, int | None, str | None],
) -> None:
    """A hashed file's size is the bytes read, a pointer's none; over the
    ceiling the ``stat()`` size, none below a pointer's largest size (only
    the forbidden read could tell); a directory has none yet. Only the
    ceiling, at ``stat()`` or in a grown read, is ``"over-cap"``."""
    top = tmp_path / "d"
    top.mkdir()
    (top / "f.bin").write_bytes(row.data)
    assert os.path.getsize(top / "f.bin") == len(row.data)
    _inject(monkeypatch, row.fault)
    with caplog.at_level(logging.WARNING):
        found = dataset_hash.hash_dataset(
            top if row.as_dir else top / "f.bin",
            max_bytes=row.max_bytes,
            sha512=row.sha512,
        )
    got = (found.kind, found.hex_digest is not None, found.size, found.omitted)
    assert got == expected
    assert found.omitted is None or found.omitted in REASON_CODES
    warned = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warned) == (0 if found.hex_digest else 1)
    pointer = parse_lfs_pointer(row.data)
    assert [p for _, p in found.lfs_pointers] == ([pointer] if pointer else [])
    if found.hex_digest and not row.as_dir:
        assert found.hex_digest == (
            pointer.oid if pointer else hashlib.sha256(row.data).hexdigest()
        )
