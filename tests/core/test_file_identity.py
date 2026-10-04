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


def test_a_missing_path_has_no_identity(tmp_path: Path) -> None:
    assert file_id(tmp_path / "missing") is None


def test_a_zero_inode_is_no_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """FAT/exFAT report 0 for every file."""
    # The module's own name, not ``os.stat``, which every thread shares.
    fake = SimpleNamespace(stat=lambda _p: SimpleNamespace(st_dev=1, st_ino=0))
    monkeypatch.setattr(file_identity, "os", fake)
    assert file_id("x") is None
