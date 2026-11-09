# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""In a temporary clone, the clone's ``.git`` directory is not inside it
for a read (:func:`~pitloom.core.path_confine.inside_clone_but_not_git`):
its ``config`` can hold the URL's user information. Out of a clone a
project's ``.git`` reads as before.

See also: :mod:`tests.core.test_path_confine` (the check itself).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.core.clone_mark import reading_remote_clone
from pitloom.core.path_confine import (
    OutsideRootError,
    open_inside,
    regular_file_inside,
)
from tests._symlink import CAN_SYMLINK

_NEEDS_SYMLINK = pytest.mark.skipif(not CAN_SYMLINK, reason="needs a symlink")


@pytest.fixture(name="clone")
def _clone(tmp_path: Path) -> Path:
    """A clone at ``clone`` with ``.git/config``, ``a.txt`` and, where one
    can be made, ``c``, a link to ``.git/config``."""
    root = tmp_path / "clone"
    (root / ".git").mkdir(parents=True)
    (root / ".git" / "config").write_bytes(b"url = https://u:SECRET@h/r\n")
    (root / "a.txt").write_bytes(b"a")
    if CAN_SYMLINK:
        (root / "c").symlink_to(root / ".git" / "config")
    return root.resolve()


_NAMES = [
    (".git/config", False),
    ("a.txt", True),
    pytest.param("c", False, marks=_NEEDS_SYMLINK),
]


@pytest.mark.parametrize("known", [True, False], ids=["root", "no-root"])
@pytest.mark.parametrize(("name", "readable"), _NAMES, ids=["git", "file", "link"])
def test_the_clones_git_directory_is_not_read(
    clone: Path, name: str, readable: bool, known: bool
) -> None:
    with reading_remote_clone(str(clone) if known else None):
        assert regular_file_inside(clone, name) is readable
        if readable:
            with open_inside(clone / name, clone) as handle:
                assert handle.read() == b"a"
        else:
            with pytest.raises(OutsideRootError):
                open_inside(clone / name, clone)


@pytest.mark.parametrize(("name", "_readable"), _NAMES, ids=["git", "file", "link"])
def test_a_local_projects_git_directory_reads_as_before(
    clone: Path, name: str, _readable: bool
) -> None:
    assert regular_file_inside(clone, name)
    with open_inside(clone / name, clone) as handle:
        assert handle.read()


def test_a_subfolder_projects_clone_git_directory_is_not_read(clone: Path) -> None:
    """The ``.git`` refused is the clone's, not the project folder's."""
    sub = clone / "sub"
    sub.mkdir()
    (sub / ".git").mkdir()
    (sub / ".git" / "x").write_bytes(b"x")
    with reading_remote_clone(str(clone)):
        assert regular_file_inside(sub, ".git/x")
        assert not regular_file_inside(clone, ".git/config")


def _case_insensitive(where: Path) -> bool:
    (where / "Probe").mkdir()
    return (where / "probe").is_dir()


def test_a_case_variant_of_git_is_not_read(clone: Path, tmp_path: Path) -> None:
    if not _case_insensitive(tmp_path):
        pytest.skip("the file system tells cases apart")
    with reading_remote_clone(str(clone)):
        with pytest.raises(OutsideRootError):
            open_inside(clone / ".GIT" / "config", clone)
