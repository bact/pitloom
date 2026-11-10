# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the size of a checkout (``_git_size``), and the cap's boundary:
a checkout of exactly ``max_bytes`` is within it, both after a call and while
one runs (``_git_run``).

See also: test_git_hardening.py (the cap on a running ``git``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path
from unittest import mock

import pytest

from pitloom.extract.remote import _git_run
from pitloom.extract.remote._git_run import GitRunner
from pitloom.extract.remote._git_size import SizeCap, tree_bytes
from pitloom.extract.remote.errors import RemoteSourceError
from tests._symlink import CAN_SYMLINK


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


_CAP = 100


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
@pytest.mark.parametrize("size", [_CAP, _CAP + 1], ids=["at-the-cap", "over"])
def test_a_checkout_of_exactly_the_cap_is_within_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, size: int
) -> None:
    """Checked once the call has ended."""
    (tmp_path / "big").write_bytes(b"x" * size)
    monkeypatch.setattr(_git_run, "_capture", lambda *_args: (0, "", ""))
    runner = GitRunner(max_bytes=_CAP)
    if size == _CAP:
        assert runner.run(["clone"], "clone", echo=False, watch=str(tmp_path)) == ""
        return
    with pytest.raises(RemoteSourceError) as info:
        runner.run(["clone"], "clone", echo=False, watch=str(tmp_path))
    assert info.value.code == "git.too-large"


@pytest.mark.parametrize("size", [_CAP, _CAP + 1], ids=["at-the-cap", "over"])
def test_the_watcher_stops_a_call_only_past_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, size: int
) -> None:
    """Checked while the call runs: the watcher looks a few times."""
    (tmp_path / "big").write_bytes(b"x" * size)
    looked = threading.Semaphore(0)
    killed: list[object] = []

    def counted(top: str) -> int:
        looked.release()
        return tree_bytes(top)

    monkeypatch.setattr(_git_run, "tree_bytes", counted)
    monkeypatch.setattr(_git_run, "_SIZE_POLL_SECONDS", 0.001)
    monkeypatch.setattr(_git_run, "_kill", killed.append)
    cap, done, proc = SizeCap(str(tmp_path), _CAP), threading.Event(), object()
    watcher = threading.Thread(
        target=_git_run._watch_size,  # pylint: disable=protected-access
        args=(proc, cap, done),
    )
    watcher.start()
    for _look in range(1 if size > _CAP else 3):
        # pylint: disable-next=consider-using-with
        assert looked.acquire(timeout=30)
    done.set()
    watcher.join(timeout=30)
    assert not watcher.is_alive()
    assert cap.exceeded is (size > _CAP) and killed == ([proc] if size > _CAP else [])
