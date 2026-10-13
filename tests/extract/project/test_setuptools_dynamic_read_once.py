# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``[tool.setuptools.dynamic]`` requirements files read once, known by
the file opened rather than by a path's spelling.

See also: tests/extract/project/test_setuptools_dynamic.py (the reader's
other rules).
"""

from __future__ import annotations

import errno
import io
import logging
import os
from pathlib import Path

import pytest

from pitloom.extract.project import _setuptools_dynamic, read_project
from tests._symlink import CAN_SYMLINK, case_sensitive

_DYN = "tool.setuptools.dynamic"


class _ReadFails(io.FileIO):
    """A listed file that opens but fails to read."""

    def read(self, size: int | None = -1) -> bytes:
        raise OSError(errno.EIO, "Input/output error")


def _link(project: Path, how: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """``b.txt``, another way to reach ``a.txt``, as *how*."""
    if how in ("hard", "no-identity"):
        os.link(project / "a.txt", project / "b.txt")
    if how == "no-identity":  # st_ino 0 (FAT/exFAT): known as written
        monkeypatch.setattr(_setuptools_dynamic, "file_id", lambda _fd: None)
    if how == "case":
        if not CAN_SYMLINK or case_sensitive(project.parent):
            pytest.skip("needs a symlink on a case-insensitive file system")
        other = project.parent / project.name.upper() / "a.txt"
        (project / "b.txt").symlink_to(other)
    if how == "read-error":
        (project / "b.txt").write_bytes(b"attrs\n")
        monkeypatch.setattr(
            _setuptools_dynamic,
            "open_inside",
            lambda written, _root: (
                _ReadFails if written.name == "b.txt" else io.FileIO
            )(written),
        )


@pytest.mark.parametrize(
    ("how", "deps", "warning"),
    [
        ("hard", ["six"], None),
        ("case", ["six"], None),
        ("no-identity", ["six", "six"], None),
        ("read-error", ["six"], f"FILE=b.txt: could not read for {_DYN}.depend"),
    ],
    ids=["hard", "case", "no-identity", "read-error"],
)
def test_one_file_is_read_once_however_it_is_reached(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    how: str,
    deps: list[str],
    warning: str | None,
) -> None:
    """Regression: a file reached by two spellings that resolve apart (a
    symlink spelling the project in another letter case) was read, and its
    bytes counted, twice. A hard link is the same file too; with no file
    identity, each spelling is its own file. A read failure warns."""
    project = tmp_path / "p"
    project.mkdir()
    (project / "a.txt").write_bytes(b"six\n")
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1"\ndynamic = ["dependencies"]\n'
        f'[{_DYN}]\ndependencies = {{file = ["a.txt", "b.txt"]}}\n',
        encoding="utf-8",
    )
    _link(project, how, monkeypatch)

    with caplog.at_level(logging.WARNING):
        metadata = read_project(project, include_locked_dependencies=False)[0]

    assert metadata.dependencies == deps
    assert len(caplog.messages) == (warning is not None)
    assert all((warning or "") in m and "Input/output" in m for m in caplog.messages)
