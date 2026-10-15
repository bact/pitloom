# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.path_confine`: the one confinement check
of the licence and ``[tool.setuptools.dynamic]`` readers.

See also: tests/extract/test_license_detect.py and
tests/extract/project/test_setuptools_dynamic.py (each reader's symlink
rows).
"""

from __future__ import annotations

import errno
import os
from pathlib import Path, PurePath
from types import SimpleNamespace

import pytest

from pitloom.core import path_confine
from pitloom.core.path_confine import (
    NotRegularFileError,
    OutsideRootError,
    is_inside,
    open_inside,
)
from tests._symlink import CAN_SYMLINK

_WIN32 = os.name == "nt"
_NEEDS_SYMLINK = pytest.mark.skipif(not CAN_SYMLINK, reason="needs a symlink")


@pytest.fixture(name="tree")
def _tree(tmp_path: Path) -> Path:
    """``root/a.txt``, ``root/sub/b.txt``, ``out/x.txt``, and ``alias``, a
    symlink to ``root`` where one can be made."""
    for name in ("root/a.txt", "root/sub/b.txt", "out/x.txt"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(name.encode())
    if CAN_SYMLINK:
        (tmp_path / "alias").symlink_to(tmp_path / "root", target_is_directory=True)
    return tmp_path.resolve()


@pytest.mark.parametrize(
    ("path", "root", "inside"),
    [
        ("root", "root", True),
        ("root/sub/b.txt", "root", True),
        ("root/missing/c.txt", "root", True),
        ("rootx/a.txt", "root", False),
        ("out/x.txt", "root", False),
        (".", "root", False),
        ("gone/a.txt", "gone", True),
        ("out/x.txt", "gone", False),
        ("root/a\0.txt", "out", False),
        pytest.param("root/a.txt", "alias", True, marks=_NEEDS_SYMLINK),
        pytest.param("root", "alias", True, marks=_NEEDS_SYMLINK),
    ],
    ids=["itself", "below", "below-missing", "prefix-only", "sibling", "parent",
         "missing-root", "missing-root-outside", "nul-never-raises",
         "other-spelling", "other-spelling-itself"],
)  # fmt: skip
def test_is_inside(tree: Path, path: str, root: str, inside: bool) -> None:
    """By spelling, else by the identity of an ancestor (*alias* spells
    *root* another way, as a case-insensitive file system does); a root
    with no identity is matched by spelling only. Never raises."""
    assert is_inside(PurePath(tree, path), PurePath(tree, root)) is inside


@_NEEDS_SYMLINK
def test_a_root_without_identity_is_matched_by_spelling(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``st_ino`` 0 (FAT/exFAT) is no identity: two spellings stay two."""
    monkeypatch.setattr(path_confine, "file_id", lambda _path: None)
    assert not is_inside(tree / "root/a.txt", tree / "alias")


@pytest.mark.parametrize(
    ("name", "link", "error"),
    [
        ("root/a.txt", None, None),
        ("root/sub/../a.txt", None, None),
        ("root/missing/../a.txt", None, None if _WIN32 else FileNotFoundError),
        ("root/sub", None, NotRegularFileError),
        ("root/gone.txt", None, FileNotFoundError),
        ("out/x.txt", None, OutsideRootError),
        pytest.param("root/l.txt", "root/a.txt", None, marks=_NEEDS_SYMLINK),
        pytest.param("root/l.txt", "out/x.txt", OutsideRootError, marks=_NEEDS_SYMLINK),
        pytest.param("root/l.txt", "out/gone.txt", FileNotFoundError,
                     marks=_NEEDS_SYMLINK),
        pytest.param("root/l.txt", "alias/a.txt", None, marks=_NEEDS_SYMLINK),
    ],
    ids=["regular", "dotdot-inside", "dotdot-missing-dir", "directory", "missing",
         "outside", "symlink-inside", "symlink-out", "dangling-out",
         "symlink-other-spelling"],
)  # fmt: skip
def test_open_inside(
    tree: Path, name: str, link: str | None, error: type[OSError] | None
) -> None:
    """Opened as written (the OS decides ``missing/..``: POSIX needs the
    directory), and read only when it is a regular file inside the root:
    a symlink out is refused, a dangling one is missing, not read."""
    if link is not None:
        (tree / name).symlink_to(tree / link)
    if error is None:
        with open_inside(tree / name, tree / "root") as handle:
            assert handle.read() == b"root/a.txt"
    else:
        with pytest.raises(error):
            open_inside(tree / name, tree / "root")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs a FIFO")
def test_a_fifo_is_refused_without_waiting_for_a_writer(tree: Path) -> None:
    """Swapped in after the regular-file check, a FIFO opens without
    blocking and is refused on the opened handle."""
    os.mkfifo(tree / "root/fifo")
    real_stat = os.stat
    fake = SimpleNamespace(
        stat=lambda _p: real_stat(tree / "root/a.txt"),
        open=os.open,
        fstat=os.fstat,
        O_NONBLOCK=os.O_NONBLOCK,
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(path_confine, "os", fake)
        with pytest.raises(NotRegularFileError):
            open_inside(tree / "root/fifo", tree / "root")


@pytest.mark.parametrize(
    ("opened", "gone", "identity", "error"),
    [
        ("out/x.txt", False, True, OutsideRootError),
        ("root/sub/b.txt", False, True, OutsideRootError),
        ("out/x.txt", True, True, OutsideRootError),
        ("root/sub/b.txt", False, False, None),
    ],
    ids=["swapped-out", "swapped-inside", "checked-file-gone",
         "no-identity-trusts-the-path"],
)  # fmt: skip
def test_the_opened_file_must_be_the_one_checked(
    tree: Path,
    monkeypatch: pytest.MonkeyPatch,
    opened: str,
    gone: bool,
    identity: bool,
    error: type[OSError] | None,
) -> None:
    """A symlink swapped while opening: the file opened (here *opened*,
    not ``a.txt``) is refused unless the path, resolved and opened again,
    is the very file opened, by ``(st_dev, st_ino)`` -- not when it is
    *gone* by then; without file identity only the resolved path is
    checked."""
    closed: list[int] = []

    def swapped(_path: str, flags: int) -> int:
        fd = os.open(tree / opened, flags)
        closed.append(fd)
        if gone:
            (tree / "root/a.txt").unlink()
        return fd

    monkeypatch.setattr(path_confine, "open_nonblocking", swapped)
    if not identity:
        real_fstat = os.fstat
        monkeypatch.setattr(
            path_confine,
            "os",
            SimpleNamespace(
                stat=os.stat,
                fstat=lambda fd: SimpleNamespace(
                    st_mode=real_fstat(fd).st_mode, st_dev=0, st_ino=0
                ),
            ),
        )
    if error is None:
        with open_inside(tree / "root/a.txt", tree / "root") as handle:
            assert handle.read() == opened.encode()
        return
    with pytest.raises(error):
        open_inside(tree / "root/a.txt", tree / "root")
    with pytest.raises(OSError) as raised:  # the refused handle was closed
        os.fstat(closed[0])
    assert raised.value.errno == errno.EBADF


def test_a_symlink_loop_while_resolving_is_an_os_error(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``resolve()`` raises ``RuntimeError`` on a loop (3.10-3.12): it
    reaches the caller as the ``OSError`` an open would raise."""

    def loop(_self: Path, strict: bool = False) -> Path:
        raise RuntimeError(f"Symlink loop ({strict})")

    monkeypatch.setattr(Path, "resolve", loop)
    with pytest.raises(OSError) as raised:
        open_inside(tree / "root/a.txt", tree / "root")
    assert raised.value.errno == errno.ELOOP
