# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The document build's report of Git LFS pointers: one ``WARNING:`` per
kind, a ``DEBUG`` line per file.

See also: tests/test_lfs_pointer_warning_surfaces.py (every surface).
"""

from __future__ import annotations

import logging

import pytest

from pitloom.assemble.spdx3._document_lfs import report_lfs_pointers
from pitloom.core.lfs_pointer import LfsPointer
from pitloom.core.project import ProjectFile

_POINTER = LfsPointer("a" * 64, 5)


def _file(name: str, *, pointer: bool = True, sha512: str | None = None) -> ProjectFile:
    return ProjectFile(
        name,
        name,
        digest_sha256="b" * 64,
        digest_sha512=sha512,
        lfs_pointer=_POINTER if pointer else None,
    )


def _lines(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == level]


@pytest.mark.parametrize(
    ("files", "warnings"),
    [
        ([], 0),
        ([_file("a.bin", pointer=False)], 0),
        ([_file("a.bin"), _file("b.bin")], 1),
        ([_file("a.bin"), _file("a.bin")], 1),
        ([_file("a.bin", sha512="c" * 128)], 1),
        ([_file("a.bin"), _file("b.bin", sha512="c" * 128)], 2),
    ],
    ids=["none", "no-pointer", "checkout", "repeated", "shipped", "both-kinds"],
)
def test_one_warning_per_kind(
    caplog: pytest.LogCaptureFixture, files: list[ProjectFile], warnings: int
) -> None:
    with caplog.at_level(logging.DEBUG):
        report_lfs_pointers(files)
    assert len(_lines(caplog, logging.WARNING)) == warnings
    assert len(_lines(caplog, logging.DEBUG)) == sum(
        f.lfs_pointer is not None for f in files
    )


def test_the_counts_name_each_kind_apart(caplog: pytest.LogCaptureFixture) -> None:
    files = [_file("c.bin"), _file("a.bin"), _file("s.bin", sha512="c" * 128)]
    report_lfs_pointers(files)
    checkout, shipped = _lines(caplog, logging.WARNING)
    assert "FILE=a.bin" in checkout and "(2 files)" in checkout
    assert "FILE=s.bin" in shipped and "files)" not in shipped
