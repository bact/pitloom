# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one summary warning for Git LFS pointers left unread."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pytest

from pitloom.core import lfs_pointer
from pitloom.core.lfs_pointer import (
    LfsPointer,
    UnreadPointers,
    log_pointer_not_read,
    reading_remote_clone,
    size_text,
    warn_pointers_not_read,
)

LOGGER = "pitloom.core.lfs_pointer"


@pytest.mark.parametrize(
    ("paths", "archive", "expected"),
    [
        (["b.bin"], False, "FILE=b.bin: Git LFS pointer, content not read;"),
        (["z", "a"], False, "FILE=a: Git LFS pointer, content not read (2 files);"),
        (["a"], True, "FILE=a: Git LFS pointer shipped; the build did not pull"),
        (["a\nERROR: x"], False, "FILE='a\\nERROR: x':"),
    ],
    ids=["one", "sorted-first", "archive", "newline"],
)
def test_summary_is_one_line_naming_the_first_path(
    caplog: pytest.LogCaptureFixture,
    paths: list[str],
    archive: bool,
    expected: str,
) -> None:
    with caplog.at_level(logging.WARNING):
        warn_pointers_not_read(paths, archive=archive)
    (record,) = caplog.records
    assert expected in record.getMessage()
    assert "\n" not in record.getMessage()


def test_no_pointer_is_silent_and_debug_line_names_the_oid(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        warn_pointers_not_read([])
        log_pointer_not_read("m.bin", LfsPointer("ab" * 32, 7))
    assert [r.levelno for r in caplog.records] == [logging.DEBUG]
    assert "oid sha256:" + "ab" * 32 in caplog.records[0].getMessage()


@pytest.mark.parametrize(
    ("size", "said"), [(0, "0 bytes"), (1, "1 byte"), (2, "2 bytes")]
)
def test_the_size_is_said_in_the_singular_for_one(
    caplog: pytest.LogCaptureFixture, size: int, said: str
) -> None:
    """The debug line and the helper every message and comment shares."""
    assert size_text(size) == said
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        log_pointer_not_read("m.bin", LfsPointer("ab" * 32, size))
    assert caplog.records[0].getMessage().endswith(f", {said}")


def _advice(caplog: pytest.LogCaptureFixture, *, archive: bool) -> str:
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        warn_pointers_not_read(["a"], archive=archive)
    return caplog.records[0].getMessage().rpartition("; ")[2]


def test_a_remote_clone_is_told_to_clone_not_to_pull(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Only a checkout's pointers change advice, only inside the context,
    which ends with the run, an error included."""
    pull = "run 'git lfs pull' for the content"
    shipped = "the build did not pull LFS content"
    assert _advice(caplog, archive=False) == pull
    with reading_remote_clone():
        assert _advice(caplog, archive=False) == (
            "clone with git lfs, then run on the directory"
        )
        assert _advice(caplog, archive=True) == shipped
    assert _advice(caplog, archive=False) == pull
    with pytest.raises(RuntimeError), reading_remote_clone():
        raise RuntimeError("boom")
    assert _advice(caplog, archive=False) == pull


@pytest.mark.parametrize("folds", [False, True], ids=["case-sensitive", "case-folding"])
def test_a_file_with_no_identity_is_keyed_by_its_folded_real_path(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, folds: bool
) -> None:
    """The fallback key, for a file ``stat()`` gives no identity (here a
    missing one): where ``normcase`` folds (Windows), ``Data.bin`` and
    ``data.bin`` are noted once, shown as first given; elsewhere two."""
    monkeypatch.setattr(lfs_pointer, "normcase", str.lower if folds else str)
    pointer = LfsPointer("ab" * 32, 7)
    noted = UnreadPointers()
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        for name in ("Data.bin", "data.bin", "Data.bin"):
            noted.note(f"/p/{name}", pointer)
        noted.warn()
    warning = caplog.records[-1].getMessage()
    assert ("/p/Data.bin" in warning) and ("(2 files)" in warning) is not folds
    assert len(caplog.records) == (2 if folds else 3)  # debug lines + summary


_NO_HARD_LINKS = sys.platform == "win32"


def _noted(paths: list[str], caplog: pytest.LogCaptureFixture) -> str:
    """The summary warning after noting every path in *paths*."""
    pointer = LfsPointer("ab" * 32, 7)
    noted = UnreadPointers()
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        for path in paths:
            noted.note(path, pointer)
        noted.warn()
    return caplog.records[0].getMessage()


@pytest.mark.parametrize("how", ["hard-link", "dot-dot"])
def test_two_spellings_of_one_file_are_noted_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, how: str
) -> None:
    """Identity, not spelling: a hard link (APFS ``Data.bin`` and
    ``data.bin`` are one inode too) and ``a/../a/x`` collapse to one note."""
    if how == "hard-link" and _NO_HARD_LINKS:
        pytest.skip("hard links need privilege on Windows")
    (tmp_path / "a").mkdir()
    first = tmp_path / "a" / "x"
    first.write_bytes(b"p")
    second = tmp_path / "a" / "y"
    if how == "hard-link":
        os.link(first, second)
    else:
        second = tmp_path / "a" / ".." / "a" / "x"
    message = _noted([str(first), str(second)], caplog)
    assert "files)" not in message
    other = tmp_path / "a" / "z"
    other.write_bytes(b"q")
    assert "(2 files)" in _noted([str(first), str(second), str(other)], caplog)


def test_the_folded_key_still_dedupes_when_the_identity_is_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "x").write_bytes(b"p")
    monkeypatch.setattr(lfs_pointer, "file_id", lambda _path: None)
    spelt = [str(tmp_path / "x"), str(tmp_path / "." / "x")]
    assert "files)" not in _noted(spelt, caplog)
