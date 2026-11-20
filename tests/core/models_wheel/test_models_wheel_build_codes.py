# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What ``--allow-build`` says when a build gives no wheel to read: each
``build-failed`` line through ``build_and_read_wheel`` (a real child
process for an exit, a negative exit, no wheel, two wheels; a fake wheel for
an empty one, a bad archive and a refused temp directory), the last line of
a hostile build log (one masked line, cut at the limit), and an
``InternalError`` that must propagate and not be swallowed as a failed build.

See also: tests/core/models_wheel/test_models_wheel_build_codes_flow.py
(``library-missing``, the timeout, the leftover processes and the
``build-code-unsafe`` variants), tests/messages/test_build.py (the lines and
fields) and tests/core/models_wheel/test_models_wheel_build_and_read.py (the
mechanism).
"""

# The private helpers are the unit under test here.
# pylint: disable=protected-access

from __future__ import annotations

import logging
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pitloom.core import _models_wheel, temp_dirs
from pitloom.core import _models_wheel_build_and_read as bar
from pitloom.core import _models_wheel_build_subprocess as bs
from pitloom.core._models_wheel_build_and_read import build_and_read_wheel
from pitloom.core.build_options import BuildOptions
from pitloom.core.internal_error import InternalError
from pitloom.messages import BUILD_FRAME, MESSAGES, trusted_message
from pitloom.messages.build import BUILD_FAILED, OUTPUT_CHARACTERS
from tests._git_say_repos import printed
from tests.build_and_read_shared import (
    RUN_BUILD,
    extract_dirs,
    install_fake_build,
    raising_build,
    use_sys_tmp,
)

pytestmark = pytest.mark.platform  # child processes, signals, line ends

_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
#: A POSIX-only test reads this one constant, never a skipif made of a name
#: Windows lacks.
_POSIX = sys.platform != "win32"
_PREFIX = BUILD_FRAME.render({})


@pytest.fixture(name="sys_tmp")
def _sys_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return use_sys_tmp(tmp_path, monkeypatch)


def _child(monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    """Make the build a child running *body* (a script, its first argument
    the wheel directory), so the real log, exit and wheel check run."""
    script = textwrap.dedent(body)

    def command(project_dir: Path, out_dir: Path, *, isolated: bool) -> list[str]:
        del project_dir, isolated
        return [sys.executable, "-c", script, str(out_dir)]

    monkeypatch.setattr(bs, "build_wheel_command", command)


def _printing(raw: bytes, status: int = 1) -> str:
    """A child script writing *raw* to its output and ending with *status*;
    the bytes are written as an escaped literal, so no argument holds a
    control character."""
    return (
        f"import sys\nsys.stdout.buffer.write({raw!r})\n"
        f"sys.stdout.flush()\nsys.exit({status})\n"
    )


def _build(project: Path, caplog: pytest.LogCaptureFixture) -> list[str]:
    """Run the build; its coded lines, as printed. The build gave no wheel."""
    caplog.clear()
    with caplog.at_level(logging.INFO):
        assert build_and_read_wheel(project, timeout=60) is None
    return printed(caplog)


def _only(lines: list[str]) -> str:
    """The one line, trusted as ``build-failed`` after ``Build: ``."""
    assert len(lines) == 1
    line = lines[0]
    assert line.startswith(f"WARNING: {_PREFIX}DIR="), line
    assert trusted_message(line) is BUILD_FAILED
    return line


@pytest.fixture(name="project")
def _project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    return project


# -- the five lines ------------------------------------------------------------


def test_no_interpreter_is_the_first_line(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    sys_tmp: Path,
) -> None:
    """The interpreter is read from the module's own ``sys``, patched there."""
    monkeypatch.setattr(bs, "sys", SimpleNamespace(executable="", platform="linux"))
    line = _only(_build(project, caplog))
    assert line.endswith(
        ": no Python interpreter to run PyPA build with; not built [build-failed]"
    )
    assert not list(sys_tmp.iterdir())


def test_a_failed_build_says_its_exit_code_and_last_line(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    sys_tmp: Path,
) -> None:
    _child(monkeypatch, _printing(b"first\nERROR boom\n\n"))
    line = _only(_build(project, caplog))
    assert line.endswith(
        ": the build exited with code 1; last output: ERROR boom [build-failed]"
    )
    assert not list(sys_tmp.iterdir())


@pytest.mark.skipif(not _POSIX, reason="a signal ends a POSIX process")
def test_a_build_ended_by_a_signal_says_a_negative_exit_code(
    project: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _child(monkeypatch, "import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n")
    line = _only(_build(project, caplog))
    assert line.endswith(
        ": the build exited with code -9; last output: (no output) [build-failed]"
    )


@pytest.mark.parametrize(
    ("body", "number"),
    [
        ("pass\n", 0),
        (
            "import os, sys\nfor n in 'ab':\n"
            "    open(os.path.join(sys.argv[1], f'{n}-1-py3-none-any.whl'), 'wb')"
            ".close()\n",
            2,
        ),
    ],
    ids=["none", "two"],
)
def test_a_build_with_not_one_wheel_says_how_many(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    body: str,
    number: int,
) -> None:
    _child(monkeypatch, body)
    line = _only(_build(project, caplog))
    assert line.endswith(f": the build wrote {number} wheels, not one [build-failed]")


def test_a_wheel_with_nothing_but_dist_info_is_a_failed_discovery(
    project: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    install_fake_build(monkeypatch).entries = {}
    line = _only(_build(project, caplog))
    assert line.endswith(
        ": the built wheel holds no file outside .dist-info; "
        "read as a failed discovery [build-failed]"
    )


def test_a_bad_wheel_archive_is_the_unusable_line_with_the_reason(
    project: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def run(work_dir: Path, **_: Any) -> Path:
        wheel = work_dir / "pkg-1.0-py3-none-any.whl"
        wheel.write_bytes(b"this is not a zip archive")
        return wheel

    monkeypatch.setattr(RUN_BUILD, lambda _p, work_dir, **kw: run(work_dir, **kw))
    line = _only(_build(project, caplog))
    assert ": the build could not run or its wheel could not be read; " in line
    assert line.endswith("[build-failed]") and "BadZipFile" not in line
    assert str(project) not in line.split("; ", 1)[1]


def test_a_refused_temp_dir_says_the_reason_and_never_the_path(
    project: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def mkdtemp(prefix: str) -> str:
        raise OSError(28, "No space left on device", f"/secret/{prefix}x")

    monkeypatch.setattr(temp_dirs, "tempfile", SimpleNamespace(mkdtemp=mkdtemp))
    line = _only(_build(project, caplog))
    assert line.endswith(
        "the build could not run or its wheel could not be read; "
        "No space left on device [build-failed]"
    )
    assert "/secret" not in caplog.text and "pitloom-build-and-read-" not in line


# -- the last line of a hostile build log --------------------------------------

_HOSTILE = [
    pytest.param(b"\x1b[31mred\x1b[0m\n", "red", id="ansi"),
    pytest.param(b"a\r\nb\r\n", "b", id="crlf"),
    pytest.param(b"boom\n\n\n   \n", "boom", id="blank-tail"),
    pytest.param(b"::error::boom\n", "::error::boom", id="workflow"),
    pytest.param(f"token={_TOKEN}\n".encode(), "token=ghp_***", id="token"),
    pytest.param(
        b"see https://u:s3cret@h/ now\n", "see https://***:***@h/ now", id="url"
    ),
    pytest.param(f"ok\t{_TOKEN}\n".encode(), "ok ghp_***", id="tab"),
    pytest.param(f"abc\x07{_TOKEN}\n".encode(), "abc ghp_***", id="bel"),
    pytest.param(b"x [over-cap]\n", "x [over-cap]", id="fake-code"),
    pytest.param(b"", "(no output)", id="empty"),
    pytest.param(
        ("y" * 190 + f" {_TOKEN} " + "z" * 60 + "\n").encode(),
        "y" * 190 + " ghp_*** z...",
        id="straddle",
    ),
    pytest.param(b"y" * 300, "y" * OUTPUT_CHARACTERS + "...", id="cut"),
]


@pytest.mark.parametrize(("raw", "shown"), _HOSTILE)
def test_a_hostile_build_log_gives_one_masked_line_cut_at_the_limit(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    raw: bytes,
    shown: str,
) -> None:
    _child(monkeypatch, _printing(raw))
    lines = _build(project, caplog)
    line = _only(lines)
    assert line.endswith(f"last output: {shown} [build-failed]"), line
    assert "s3cret" not in caplog.text
    assert _TOKEN not in line and "ghp_A1" not in line and "\x1b" not in line
    # Tagged lines only: a build's own ``::`` line is no line of its own.
    levels = {r.levelname for r in caplog.records if r.levelno >= logging.INFO}
    assert levels == {"WARNING"} and len(printed(caplog)) == 1


def test_a_fake_code_in_the_log_does_not_forge_the_code(
    project: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _child(monkeypatch, _printing(b"done [over-cap]\n"))
    line = _only(_build(project, caplog))
    assert line.count(" [over-cap]") == 1 and line.endswith(" [build-failed]")
    assert trusted_message(line) is MESSAGES["build-failed"]


# -- an InternalError is no failed build ---------------------------------------


def test_an_internal_error_in_the_build_propagates_and_cleans_up(
    project: Path, monkeypatch: pytest.MonkeyPatch, sys_tmp: Path
) -> None:
    """A bug of Pitloom's own, not a failure to report as ``build-failed``:
    ``InternalError`` is a ``ValueError``, which the broad ``except`` after
    it would have caught."""
    seen: set[str] = set()
    monkeypatch.setattr(RUN_BUILD, raising_build(InternalError("bug"), sys_tmp, seen))
    with pytest.raises(InternalError, match="bug"):
        build_and_read_wheel(project, timeout=60)
    assert seen and not list(sys_tmp.iterdir())


def test_an_internal_error_from_the_empty_wheel_line_propagates(
    project: Path, monkeypatch: pytest.MonkeyPatch, sys_tmp: Path
) -> None:
    """An emit inside the build's own ``try`` (the line of an empty wheel)."""
    install_fake_build(monkeypatch).entries = {}

    def refuse(*_args: object, **_kw: object) -> None:
        raise InternalError("a frame that does not allow the line")

    monkeypatch.setattr(bar, "emit", refuse)
    with pytest.raises(InternalError, match="does not allow"):
        build_and_read_wheel(project, timeout=60)
    assert not list(sys_tmp.iterdir())


def test_an_internal_error_from_the_failure_line_propagates(
    project: Path, monkeypatch: pytest.MonkeyPatch, sys_tmp: Path
) -> None:
    """An emit in the handler that says the failure."""
    _child(monkeypatch, _printing(b"x\n"))

    def refuse(*_args: object, **_kw: object) -> None:
        raise InternalError("bad value")

    monkeypatch.setattr(bar, "emit", refuse)
    with pytest.raises(InternalError, match="bad value"):
        build_and_read_wheel(project, timeout=60)
    assert not list(sys_tmp.iterdir()) and not extract_dirs(sys_tmp)


def test_a_plain_build_failure_is_not_an_internal_error(
    project: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The other side: any other exception is a failed build, not a crash."""

    def run(*_args: object, **_kw: object) -> Path:
        raise RuntimeError("backend died")

    monkeypatch.setattr(RUN_BUILD, run)
    line = _only(_build(project, caplog))
    assert line.endswith("; backend died [build-failed]")


def test_an_internal_error_reaches_the_caller_of_get_wheel_files(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The library entry point's broad ``except`` (a failed discovery is an
    empty result) must not turn a refused frame into one."""

    def refuse(*_args: object, **_kw: object) -> None:
        raise InternalError("a frame that does not allow the line")

    monkeypatch.setattr(_models_wheel, "_discover_included_files", refuse)
    with pytest.raises(InternalError, match="does not allow"):
        _models_wheel.get_wheel_files(project, build_options=BuildOptions(allow=True))
