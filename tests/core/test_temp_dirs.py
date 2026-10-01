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
from pathlib import Path
from unittest import mock

import pytest

from pitloom.core import temp_dirs
from pitloom.core.build_signals import BUILD_ACTIVITY, TerminationGuard
from pitloom.core.temp_dirs import one_shot, registered_temp_dir
from tests.build_and_read_shared import use_sys_tmp


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
    assert f"Scan: could not fully remove temporary directory {path.name} " in (
        caplog.text
    )
    assert str(sys_tmp) not in caplog.text
    assert "Build:" not in caplog.text
