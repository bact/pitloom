# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Git LFS pointer test data: a missing fixture directory fails in a Git
checkout and skips only the tests that read it in a sdist.

See also: tests/_lfs.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import _lfs


@pytest.mark.parametrize("entry", [None, "dir", "file"], ids=["none", "dir", "file"])
def test_a_git_checkout_is_a_parent_with_a_git_entry(
    tmp_path: Path, entry: str | None
) -> None:
    root = tmp_path / "a" / "b"
    root.mkdir(parents=True)
    if entry is None and _lfs.in_git_checkout(tmp_path):
        pytest.skip("the temporary directory is inside a Git checkout")
    if entry == "dir":
        (tmp_path / "a" / ".git").mkdir()
    elif entry == "file":  # a worktree
        (root / ".git").write_bytes(b"gitdir: x\n")
    assert _lfs.in_git_checkout(root) is (entry is not None)


@pytest.mark.parametrize("checkout", [True, False], ids=["checkout", "sdist"])
def test_a_missing_fixture_fails_in_a_checkout_and_skips_in_a_sdist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, checkout: bool
) -> None:
    monkeypatch.setattr(_lfs, "_FIXTURES", tmp_path)
    monkeypatch.setattr(_lfs, "in_git_checkout", lambda _root: checkout)
    with pytest.raises((pytest.fail.Exception, pytest.skip.Exception)) as caught:
        _lfs.pointer_fixture("missing.bin")
    assert caught.type is (pytest.fail.Exception if checkout else pytest.skip.Exception)


def test_the_data_is_a_fresh_copy_on_each_call() -> None:
    """A caller may change what it gets."""
    first = _lfs.tree()
    first.clear()
    assert _lfs.tree() and set(_lfs.pointers()) <= set(_lfs.tree())
