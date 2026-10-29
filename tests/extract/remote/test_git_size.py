# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the size of a checkout (``_git_size``).

See also: test_git_hardening.py (the cap on a running ``git``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from pitloom.extract.remote._git_size import readable_bytes, tree_bytes
from tests._symlink import CAN_SYMLINK


@pytest.mark.parametrize(
    ("count", "text"),
    [
        (0, "0 bytes"),
        (1, "1 byte"),
        (1023, "1023 bytes"),
        (1024, "1 KiB"),
        (1025, "1025 bytes"),
        (512 * 1024 * 1024, "512 MiB"),
        (3 * 1024**3, "3 GiB"),
    ],
)
def test_readable_bytes(count: int, text: str) -> None:
    assert readable_bytes(count) == text


def test_tree_bytes_counts_every_file_below(tmp_path: Path) -> None:
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "x").write_bytes(b"1" * 10)
    (tmp_path / "y").write_bytes(b"2" * 5)
    assert tree_bytes(str(tmp_path)) == 15


def test_tree_bytes_of_a_missing_directory_is_nothing(tmp_path: Path) -> None:
    assert tree_bytes(str(tmp_path / "absent")) == 0


@pytest.mark.skipif(not CAN_SYMLINK, reason="needs a symlink")
def test_tree_bytes_does_not_follow_a_link(tmp_path: Path) -> None:
    """A link out of the checkout is the size of the link, not of its target."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "big").write_bytes(b"x" * 1000)
    inside = tmp_path / "inside"
    inside.mkdir()
    (inside / "dir").symlink_to(outside, target_is_directory=True)
    (inside / "file").symlink_to(outside / "big")
    assert tree_bytes(str(inside)) < 1000


def test_tree_bytes_skips_an_entry_it_cannot_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = mock.Mock(path="unreadable")
    entry.is_dir.side_effect = PermissionError
    listing = mock.MagicMock()
    listing.__enter__.return_value = [entry]
    listing.__exit__.return_value = False
    monkeypatch.setattr(os, "scandir", lambda _path: listing)
    assert tree_bytes(str(tmp_path)) == 0
