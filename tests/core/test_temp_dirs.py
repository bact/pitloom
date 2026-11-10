# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``pitloom.core.temp_dirs``.

See also: tests/core/models_wheel/test_models_wheel_build_and_read_cleanup.py
(the build-and-read caller's cleanup, signals included) and
tests/core/test_build_signals.py (the guard itself).
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from pitloom.core import temp_dirs
from pitloom.core.build_signals import BUILD_ACTIVITY, TerminationGuard
from pitloom.core.temp_dirs import one_shot, registered_temp_dir, temp_dir
from tests._symlink import CAN_SYMLINK
from tests.build_and_read_shared import use_sys_tmp

_PREFIX = "Fetch: "


@pytest.fixture(name="sys_tmp")
def _sys_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return use_sys_tmp(tmp_path, monkeypatch)


def test_registered_temp_dir_removed_when_owner_block_fails(sys_tmp: Path) -> None:
    """The owner's block ending by an exception runs the registered removal."""
    created: list[Path] = []
    with pytest.raises(RuntimeError), TerminationGuard() as termination:
        with termination.hold(BUILD_ACTIVITY):
            path, _ = registered_temp_dir(termination, "t-", log_prefix="Scan: ")
        created.append(path)
        assert path.is_dir() and path.parent == sys_tmp
        assert path.name.startswith("t-")
        raise RuntimeError("owner failed")

    assert created and not created[0].exists()


def test_one_shot_runs_once() -> None:
    remove = mock.Mock()
    cleanup = one_shot(remove)
    cleanup()
    cleanup()
    remove.assert_called_once_with()


def test_one_shot_reruns_after_interrupted_run() -> None:
    """A run cut short is not marked done, so the next run repeats it."""
    remove = mock.Mock(side_effect=[KeyboardInterrupt, None])
    cleanup = one_shot(remove)
    with pytest.raises(KeyboardInterrupt):
        cleanup()
    cleanup()
    cleanup()
    assert remove.call_count == 2


def test_leftover_warning_uses_given_log_prefix(
    sys_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(temp_dirs, "rmtree_quietly", lambda path, log_prefix: None)
    with TerminationGuard() as termination, termination.hold(BUILD_ACTIVITY):
        path, remove = registered_temp_dir(termination, "t-", log_prefix="Scan: ")
    with caplog.at_level(logging.WARNING):
        remove()

    assert path.parent == sys_tmp
    assert f"Scan: could not fully remove temporary directory '{path.name}' " in (
        caplog.text
    )
    assert str(sys_tmp) not in caplog.text
    assert "Build:" not in caplog.text


def test_temp_dir_is_removed_on_exit(sys_tmp: Path) -> None:
    with temp_dir("t-", log_prefix=_PREFIX) as path:
        assert path.is_dir() and path.parent == sys_tmp
        assert path.name.startswith("t-")
        (path / "f").write_bytes(b"x")
    assert not os.path.lexists(path)


def test_temp_dir_is_removed_when_the_block_fails(sys_tmp: Path) -> None:
    made: list[Path] = []
    with pytest.raises(RuntimeError, match="owner failed"):
        with temp_dir("t-", log_prefix=_PREFIX) as path:
            made.append(path)
            raise RuntimeError("owner failed")
    assert made[0].parent == sys_tmp and not os.path.lexists(made[0])


def _deep_rmtree(*_args: object, **_kwargs: object) -> None:
    """``shutil.rmtree`` raising past ``ignore_errors`` (Python 3.10, a tree
    deeper than the recursion limit)."""
    raise RecursionError("maximum recursion depth exceeded")


@pytest.mark.parametrize("raises", [False, True], ids=["left-behind", "rmtree-raises"])
def test_temp_dir_left_behind_warns_once_and_never_raises(
    sys_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    raises: bool,
) -> None:
    """The block's result stands: one ``WARNING:`` names the directory, not
    its path."""
    if raises:
        monkeypatch.setattr(temp_dirs, "shutil", SimpleNamespace(rmtree=_deep_rmtree))
    else:
        monkeypatch.setattr(temp_dirs, "rmtree_quietly", lambda _path, _prefix: None)
    with caplog.at_level(logging.WARNING), temp_dir("t-", log_prefix=_PREFIX) as path:
        pass
    assert path.is_dir()
    assert [r.getMessage() for r in caplog.records] == [
        f"{_PREFIX}could not fully remove temporary directory '{path.name}' "
        "(in the system temp directory)"
    ]
    assert str(sys_tmp) not in caplog.text


def _windows_rmtree(path: str | Path, ignore_errors: bool = False) -> None:
    """``shutil.rmtree`` as on Windows, where a read-only file or folder
    cannot be deleted: nothing is removed while one is at or below *path*."""
    assert ignore_errors
    for here, _folders, files in os.walk(path):
        for entry in (here, *(os.path.join(here, name) for name in files)):
            if not os.path.islink(entry) and not (
                os.lstat(entry).st_mode & stat.S_IWUSR
            ):
                return
    shutil.rmtree(path, ignore_errors=True)


def test_a_read_only_file_is_made_writable_and_removed(
    sys_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A Git pack file is read-only; on Windows rmtree leaves it, so the
    removal makes what is left writable and tries again, quietly. A
    read-only folder, the directory itself included, too."""
    monkeypatch.setattr(temp_dirs, "shutil", SimpleNamespace(rmtree=_windows_rmtree))
    with caplog.at_level(logging.WARNING), temp_dir("t-", log_prefix=_PREFIX) as path:
        pack = path / ".git" / "objects" / "pack"
        pack.mkdir(parents=True)
        (pack / "pack-1.pack").write_bytes(b"x")
        for read_only in (pack / "pack-1.pack", pack, path):
            os.chmod(read_only, stat.S_IREAD | stat.S_IEXEC)
    assert path.parent == sys_tmp and not os.path.lexists(path)
    assert not caplog.records


@pytest.mark.skipif(not CAN_SYMLINK, reason="needs symlink privilege")
def test_making_writable_leaves_a_link_target_alone(tmp_path: Path) -> None:
    """A link out of the directory keeps its target's mode: ``chmod``
    follows a link."""
    outside = tmp_path / "outside"
    outside.write_bytes(b"host file")
    os.chmod(outside, stat.S_IREAD)
    before = os.stat(outside).st_mode
    inside = tmp_path / "t-dir"
    (inside / "sub").mkdir(parents=True)
    (inside / "sub" / "link").symlink_to(outside)
    (inside / "ro").write_bytes(b"x")
    os.chmod(inside / "ro", stat.S_IREAD)
    temp_dirs._make_writable(inside)  # pylint: disable=protected-access
    assert os.stat(outside).st_mode == before
    assert os.stat(inside / "ro").st_mode & stat.S_IWUSR
