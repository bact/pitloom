# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for :func:`pitloom.core.file_identity.file_id`."""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from pitloom.core import file_identity
from pitloom.core.file_identity import file_id


def test_a_hard_link_has_the_identity_of_its_file(tmp_path: Path) -> None:
    first = tmp_path / "a"
    first.write_bytes(b"x")
    second = tmp_path / "b"
    other = tmp_path / "c"
    other.write_bytes(b"x")
    os.link(first, second)

    assert file_id(first) is not None
    assert file_id(first) == file_id(second)
    assert file_id(first) != file_id(other)
    # An open descriptor: its file. Compared with another descriptor, as
    # Windows may fill a path's identity from another API than fstat().
    with first.open("rb") as one, second.open("rb") as two:
        assert file_id(one.fileno()) is not None
        assert file_id(one.fileno()) == file_id(two.fileno())


@pytest.mark.parametrize("name", ["missing", "a\0b"], ids=["missing", "nul"])
def test_a_path_that_cannot_be_stat_ed_has_no_identity(
    tmp_path: Path, name: str
) -> None:
    """Never raises: an embedded NUL is no file either."""
    assert file_id(tmp_path / name) is None


def test_a_zero_inode_is_no_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """FAT/exFAT report 0 for every file."""
    # The module's own name, not ``os.stat``, which every thread shares.
    fake = SimpleNamespace(stat=lambda _p: SimpleNamespace(st_dev=1, st_ino=0))
    monkeypatch.setattr(file_identity, "os", fake)
    assert file_id("x") is None
