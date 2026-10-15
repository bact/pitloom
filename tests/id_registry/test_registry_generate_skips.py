# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for what the ``id generate`` walk leaves out or refuses:

* the declared registry is left out by identity, never by its name;
* a PATH with an ignored directory name gets one warning;
* a file name a registry cannot hold (not UTF-8 encodable) is skipped
  with the shared ``FILE=`` warning;
* a PATH that itself cannot be read or listed raises.

See also: test_registry_generate.py, test_registry_iter_files.py.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

import pitloom.id_registry._types as types_mod
from pitloom.id_registry import DEFAULT_ID_REGISTRY_FILENAME
from pitloom.id_registry._types import _iter_files
from tests._unreadable import POSIX_NON_ROOT

_POSIX = pytest.mark.skipif(not POSIX_NON_ROOT, reason="needs POSIX, non-root")


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "src" / "sub").mkdir(parents=True)
    (root / "src" / "a.py").write_bytes(b"a\n")
    return root


def test_registry_is_excluded_by_identity_not_by_name(tmp_path: Path) -> None:
    root = _project(tmp_path)
    stray = root / "src" / "sub" / DEFAULT_ID_REGISTRY_FILENAME
    stray.write_bytes(b"{}")
    declared = root / "src" / "my-ids.json"
    declared.write_bytes(b"{}")

    files = list(_iter_files([root / "src"], root, declared))

    assert stray in files  # a stray file of that name is an ordinary file
    assert declared not in files
    assert root / "src" / "a.py" in files


def test_file_named_twice_is_yielded_once(tmp_path: Path) -> None:
    root = _project(tmp_path)
    a_py = root / "src" / "a.py"

    files = list(_iter_files([root / "src", a_py, a_py], root, None))

    assert files.count(a_py) == 1


@pytest.mark.parametrize("below", [False, True], ids=["root", "below-root"])
def test_path_with_ignored_directory_name_warns_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, below: bool
) -> None:
    root = _project(tmp_path)
    target = root / "build" / "x" if below else root / "build"
    target.mkdir(parents=True)
    (target / "c.py").write_bytes(b"c\n")

    with caplog.at_level(logging.WARNING):
        files = list(_iter_files([target], root))

    assert not files
    (warning,) = [r.getMessage() for r in caplog.records]
    assert "skipped directory name (build)" in warning


def test_project_itself_named_like_an_ignored_directory_does_not_warn(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = tmp_path / "build"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_bytes(b"a\n")

    with caplog.at_level(logging.WARNING):
        assert list(_iter_files([root / "src"], root)) == [root / "src" / "a.py"]
    assert not caplog.records


def test_unencodable_name_is_skipped_with_the_file_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A fake listing: such a name can only exist on some file systems."""
    root = _project(tmp_path)
    bad = root / "src" / "bad\udcff.py"
    good = root / "src" / "a.py"
    monkeypatch.setattr(types_mod, "_walk_files", lambda *_: [good, bad])

    with caplog.at_level(logging.WARNING):
        files = list(_iter_files([root / "src"], root))

    assert files == [good]
    (warning,) = [r.getMessage() for r in caplog.records]
    assert warning.startswith("FILE='src/bad")
    assert "cannot be encoded as UTF-8" in warning


@_POSIX
@pytest.mark.parametrize("kind", ["dir", "file"])
def test_unreadable_path_raises(tmp_path: Path, kind: str) -> None:
    root = _project(tmp_path)
    target = root / "src" / "sub" if kind == "dir" else root / "src" / "a.py"
    target.chmod(0)
    try:
        with pytest.raises(ValueError, match="PATH .*could not be read"):
            list(_iter_files([target], root))
    finally:
        target.chmod(0o755)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs mkfifo")
def test_non_regular_path_is_not_opened(tmp_path: Path) -> None:
    """Opening a FIFO would block: the read probe is for regular files."""
    root = _project(tmp_path)
    fifo = root / "src" / "pipe"
    os.mkfifo(fifo)  # type: ignore[attr-defined,unused-ignore]

    assert not list(_iter_files([fifo], root))
