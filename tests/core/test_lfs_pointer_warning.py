# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one summary warning for Git LFS pointers left unread."""

from __future__ import annotations

import logging

import pytest

from pitloom.core.lfs_pointer import (
    LfsPointer,
    log_pointer_not_read,
    warn_pointers_not_read,
)


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
    with caplog.at_level(logging.DEBUG):
        warn_pointers_not_read([])
        log_pointer_not_read("m.bin", LfsPointer("ab" * 32, 7))
    assert [r.levelno for r in caplog.records] == [logging.DEBUG]
    assert "oid sha256:" + "ab" * 32 in caplog.records[0].getMessage()
