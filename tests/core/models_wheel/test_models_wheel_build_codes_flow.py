# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What ``--allow-build`` says around a build: ``build-code-unsafe`` before
it (each of the four variants), ``library-missing`` (PyPA build not
installed, the warning line coded, the file-discovery fallback line after
it), ``build-timeout`` (both lines) and ``build-processes-unsafe`` (the
processes a finished build left: killed, not confirmed, a refused ``killpg``).

See also: tests/core/models_wheel/test_models_wheel_build_codes.py (the
``build-failed`` lines and an ``InternalError``),
tests/core/models_wheel/test_models_wheel_build_kill.py (the kill path) and
tests/messages/test_build.py (the lines and fields).
"""

# The private helpers are the unit under test here.
# pylint: disable=protected-access

from __future__ import annotations

import errno
import logging
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from pitloom.core import _models_wheel_build_kill as bk
from pitloom.core import _models_wheel_build_subprocess as bs
from pitloom.core._models_wheel_build_and_read import build_and_read_wheel
from pitloom.core._models_wheel_build_subprocess import BuildTimeoutError
from pitloom.core._models_wheel_dispatch import _try_build_and_read
from pitloom.core._models_wheel_types import BuildSettings
from pitloom.core.build_options import BuildOptions
from pitloom.core.build_signals import TerminationGuard
from pitloom.core.models import get_wheel_files
from pitloom.messages import BUILD_FRAME, code_of, trusted_message
from pitloom.messages.build import (
    BUILD_CODE_UNSAFE,
    BUILD_PROCESSES_UNSAFE,
    BUILD_TIMEOUT,
    unsafe_line,
)
from pitloom.messages.models import LIBRARY_MISSING
from tests._git_say_repos import printed
from tests._pid import wait_pid_gone
from tests.build_and_read_shared import (
    BUILD_AND_READ,
    RUN_BUILD,
    make_backend_project,
    use_sys_tmp,
)

pytestmark = pytest.mark.platform  # child processes, process groups

#: A POSIX-only test reads this one constant, never a skipif made of a name
#: Windows lacks.
_POSIX = sys.platform != "win32"
_PREFIX = BUILD_FRAME.render({})
_POSIX_ONLY = pytest.mark.skipif(not _POSIX, reason="process groups are POSIX-only")


@pytest.fixture(name="sys_tmp")
def _sys_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return use_sys_tmp(tmp_path, monkeypatch)


# -- build-code-unsafe: one line of four ---------------------------------------


@pytest.mark.parametrize("static_failed", [False, True], ids=["no-module", "static"])
@pytest.mark.parametrize("isolated", [True, False], ids=["isolated", "shared"])
def test_a_build_says_the_unsafe_line_of_its_two_choices_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    static_failed: bool,
    isolated: bool,
) -> None:
    before_build: list[list[str]] = []

    def build(project: Path, **kw: object) -> None:
        before_build.append(printed(caplog))
        del project, kw

    monkeypatch.setattr(BUILD_AND_READ, build)
    settings = BuildSettings(isolated=isolated, timeout=77)
    with caplog.at_level(logging.INFO):
        _try_build_and_read(
            "mesonpy", tmp_path, build=settings, static_failed=static_failed
        )
    lines = printed(caplog)
    assert len(lines) == 1
    line = lines[0]
    # A library call: the library's wording.
    text = unsafe_line(static_failed=static_failed, isolated=isolated).library.render(
        {"dir": tmp_path, "duration": 77, "backend": "mesonpy"}
    )
    assert line == f"WARNING: {_PREFIX}{text} [build-code-unsafe]"
    assert trusted_message(line) is BUILD_CODE_UNSAFE
    assert "(build-backend mesonpy, " in line and "up to 77 seconds" in line
    assert before_build == [[line]]  # said before the build starts
    assert ("its static discovery failed" in line) is static_failed
    assert ("Pitloom's own environment" in line) is not isolated


# -- library-missing -----------------------------------------------------------


def _uv_project(root: Path) -> Path:
    make_backend_project(root, "uv_build")
    return root


def test_pypa_build_missing_is_a_coded_warning_then_the_fallback_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Printed uncoded before the catalogue; now ``[library-missing]``, and
    the file-discovery line that says the fallback follows it."""
    project = _uv_project(tmp_path)
    monkeypatch.setattr(bs, "find_spec", lambda _name: None)
    monkeypatch.setattr(
        "pitloom.core._models_wheel_hatchling.discover", lambda _dir: []
    )
    with caplog.at_level(logging.INFO):
        get_wheel_files(project, build_options=BuildOptions(allow=True))
    lines = printed(caplog)
    codes = [line.rsplit(" [", 1)[1].rstrip("]") for line in lines]
    assert codes[0] == "build-code-unsafe" and codes[1] == "library-missing"
    assert len(codes) == 3 and codes[2] not in {"build-failed", "library-missing"}
    assert lines[1] == (
        f"WARNING: {_PREFIX}required library not installed: build; "
        "install pitloom[build] [library-missing]"
    )
    assert trusted_message(lines[1]) is LIBRARY_MISSING


def test_pypa_build_missing_is_said_once_and_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    sys_tmp: Path,
) -> None:
    monkeypatch.setattr(bs, "find_spec", lambda _name: None)
    with caplog.at_level(logging.INFO):
        assert build_and_read_wheel(tmp_path, timeout=60) is None
    lines = printed(caplog)
    assert len(lines) == 1
    line = lines[0]
    assert line.endswith("[library-missing]") and not list(sys_tmp.iterdir())


def test_a_namespace_package_build_is_no_pypa_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A bare ``build/`` directory (no origin) is not the library: the
    same line."""
    monkeypatch.setattr(bs, "find_spec", lambda _name: SimpleNamespace(origin=None))
    with caplog.at_level(logging.INFO):
        assert build_and_read_wheel(tmp_path, timeout=60) is None
    assert [line.rsplit(" [", 1)[1] for line in printed(caplog)] == ["library-missing]"]


# -- build-timeout -------------------------------------------------------------


@pytest.mark.parametrize(
    ("tree_terminated", "ending"),
    [
        (True, "its process tree was stopped"),
        (False, "could not confirm its process tree stopped"),
    ],
    ids=["stopped", "unconfirmed"],
)
def test_a_timeout_says_the_line_of_its_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    sys_tmp: Path,
    tree_terminated: bool,
    ending: str,
) -> None:
    def run(*_args: object, **_kw: object) -> Path:
        raise BuildTimeoutError(5, tree_terminated=tree_terminated)

    monkeypatch.setattr(RUN_BUILD, run)
    with caplog.at_level(logging.INFO):
        assert build_and_read_wheel(tmp_path, timeout=5) is None
    lines = printed(caplog)
    assert len(lines) == 1
    line = lines[0]
    assert line == (
        f"WARNING: {_PREFIX}DIR={tmp_path}: the build timed out after 5 seconds "
        f"(BuildOptions.timeout); {ending} [build-timeout]"
    )
    assert "timed out after" in line and trusted_message(line) is BUILD_TIMEOUT
    assert not list(sys_tmp.iterdir())


def test_a_timeout_error_has_no_text_to_say() -> None:
    error = BuildTimeoutError(7, tree_terminated=False)
    assert str(error) == "" and (error.timeout, error.tree_terminated) == (7, False)


# -- build-processes-unsafe ----------------------------------------------------


def _fake_os(**names: object) -> SimpleNamespace:
    """The ``os`` of the kill module, with *names* instead of the real
    calls (the real ``os`` is shared by every thread)."""
    return SimpleNamespace(WNOHANG=1, waitpid=mock.Mock(), **names)


def _leftover(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    *,
    killpg: object,
    gone: bool | None,
) -> list[str]:
    """What ``kill_leftover_descendants`` prints for a group 4321, *killpg*
    its signal call and *gone* the poll's answer (``None``: not reached)."""
    monkeypatch.setattr(bk, "os", _fake_os(killpg=killpg))
    monkeypatch.setattr(bk, "_reap_group_children", lambda _pgid: None)
    monkeypatch.setattr(bk, "_GROUP_GONE_ERRORS", (ProcessLookupError,))
    waited = mock.Mock(return_value=gone)
    monkeypatch.setattr(bk, "_wait_for_group_exit", waited)
    proc = mock.create_autospec(subprocess.Popen, instance=True)
    proc.pid = 4321
    with caplog.at_level(logging.INFO):
        bk.kill_leftover_descendants(proc)
    return printed(caplog)


_LEFT = re.compile(
    r"INFO: Build: the build left processes running \(process group [1-9][0-9]*\); "
    r"killed \[build-processes-unsafe\]"
)
_KILLED = "INFO: Build: the build left processes running (process group 4321); killed"
_UNSURE = (
    "WARNING: Build: the build left processes running (process group 4321); "
    "could not confirm they stopped"
)


@_POSIX_ONLY
def test_processes_the_build_left_are_killed_once_with_an_info_line(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    lines = _leftover(monkeypatch, caplog, killpg=mock.Mock(), gone=True)
    assert lines == [f"{_KILLED} [build-processes-unsafe]"]
    assert trusted_message(lines[0]) is BUILD_PROCESSES_UNSAFE


@_POSIX_ONLY
def test_processes_not_confirmed_gone_are_a_warning_after_the_info_line(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    lines = _leftover(monkeypatch, caplog, killpg=mock.Mock(), gone=False)
    assert lines == [
        f"{_KILLED} [build-processes-unsafe]",
        f"{_UNSURE} [build-processes-unsafe]",
    ]
    assert [trusted_message(line) for line in lines] == [BUILD_PROCESSES_UNSAFE] * 2


@_POSIX_ONLY
def test_a_refused_kill_is_the_warning_alone(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """``killpg`` fails with an error that is not "no such group": no INFO
    line (nothing was killed), the warning once."""
    refused = mock.Mock(side_effect=OSError(errno.EIO, "I/O error"))
    lines = _leftover(monkeypatch, caplog, killpg=refused, gone=None)
    assert lines == [f"{_UNSURE} [build-processes-unsafe]"]
    assert trusted_message(lines[0]) is BUILD_PROCESSES_UNSAFE


@_POSIX_ONLY
def test_no_group_left_says_nothing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    gone = mock.Mock(side_effect=ProcessLookupError())
    assert not _leftover(monkeypatch, caplog, killpg=gone, gone=None)


@_POSIX_ONLY
def test_a_real_build_that_leaves_a_process_running_kills_it_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    pid_file = tmp_path / "left.pid"
    script = textwrap.dedent(
        """
        import subprocess, sys
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"]
        )
        with open(sys.argv[1], "w") as f:
            f.write(str(child.pid))
        """
    )

    def command(project_dir: Path, out_dir: Path, *, isolated: bool) -> list[str]:
        del project_dir, out_dir, isolated
        return [sys.executable, "-c", script, str(pid_file)]

    monkeypatch.setattr(bs, "build_wheel_command", command)
    work = tmp_path / "work"
    (work / "t").mkdir(parents=True)
    with caplog.at_level(logging.INFO), pytest.raises(Exception) as caught:
        bs.run_build_subprocess(
            tmp_path, work, isolated=False, timeout=60, termination=TerminationGuard()
        )
    # No wheel: the caller says that, as build-failed.
    assert code_of(caught.value) == "build-failed"
    lines = printed(caplog)
    assert len(lines) == 1
    line = lines[0]
    assert _LEFT.fullmatch(line), line
    assert trusted_message(line) is BUILD_PROCESSES_UNSAFE
    assert wait_pid_gone(int(pid_file.read_text(encoding="ascii")))
