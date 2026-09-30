# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Ctrl-C (``KeyboardInterrupt``) at the CLI entry points:
``main()`` (in-process, exit status 130) and ``console_main()`` (the
console scripts and ``python -m pitloom``, ending by SIGINT).

See also: tests/core/test_build_signals.py (``TerminationGuard``, which
leaves SIGINT to Python) and tests/assemble/test_build_termination.py.
"""

from __future__ import annotations

import os
import signal
import subprocess  # nosec B404
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest

from pitloom import __main__
from pitloom.cli.commands import project as mod_project
from pitloom.core.build_signals import BUILD_ACTIVITY, TerminationGuard
from pitloom.logging_config import PITLOOM_DEBUG_ENV_VAR
from tests.build_and_read_shared import pitloom_subprocess_env, spied_raise_signal
from tests.cli.shared import _make_simple_project


@pytest.fixture(name="raise_spy")
def fixture_raise_spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[mock.Mock]:
    with spied_raise_signal(monkeypatch) as spy:
        yield spy


def _run_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *top_level: str
) -> int:
    project_dir = _make_simple_project(tmp_path)
    out = tmp_path / "out.spdx3.json"
    monkeypatch.setattr(
        sys, "argv", ["loom", *top_level, "project", str(project_dir), "-o", str(out)]
    )
    try:
        exit_code = __main__.main()
    except KeyboardInterrupt:
        # Escaping main() would abort the whole pytest session.
        pytest.fail("KeyboardInterrupt escaped main()")
    assert not out.exists()
    return exit_code


def _interrupt(*args: object, **kwargs: object) -> str:
    del args, kwargs
    raise KeyboardInterrupt


@pytest.mark.parametrize(
    ("top_level", "env", "traceback_shown"),
    [
        pytest.param((), None, False, id="default"),
        pytest.param(("--debug",), None, True, id="debug-flag"),
        pytest.param((), "1", True, id="debug-env"),
        pytest.param(("--no-debug",), "1", False, id="no-debug-beats-env"),
    ],
)
def test_ctrl_c_is_one_error_line_and_exit_130(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    top_level: tuple[str, ...],
    env: str | None,
    traceback_shown: bool,
) -> None:
    """Ctrl-C in a subcommand is ``ERROR: interrupted`` and 130, never a
    raw traceback; the traceback follows it only when debugging."""
    if env is None:
        monkeypatch.delenv(PITLOOM_DEBUG_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(PITLOOM_DEBUG_ENV_VAR, env)
    monkeypatch.setattr(mod_project, "generate_project_sbom", _interrupt)

    assert _run_project(monkeypatch, tmp_path, *top_level) == 130

    err = capsys.readouterr().err
    assert [ln for ln in err.splitlines() if ln.startswith("ERROR:")] == [
        "ERROR: interrupted"
    ]
    assert ("Traceback" in err) is traceback_shown
    assert ("KeyboardInterrupt" in err) is traceback_shown


@pytest.mark.usefixtures("raise_spy")
def test_ctrl_c_under_termination_guard_cleans_up_first(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ctrl-C during a held build: the guard's cleanups run and its
    SIGTERM handler is restored before the ``ERROR:`` line is printed."""
    monkeypatch.delenv(PITLOOM_DEBUG_ENV_VAR, raising=False)
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
    stderr_at_cleanup: list[str] = []

    def _interrupt_build(*args: object, **kwargs: object) -> str:
        with TerminationGuard() as guard, guard.hold(BUILD_ACTIVITY):
            guard.add_cleanup(lambda: stderr_at_cleanup.append(capsys.readouterr().err))
            assert signal.getsignal(signal.SIGTERM) != signal.SIG_DFL
            return _interrupt(*args, **kwargs)

    monkeypatch.setattr(mod_project, "generate_project_sbom", _interrupt_build)

    assert _run_project(monkeypatch, tmp_path) == 130

    assert len(stderr_at_cleanup) == 1
    assert "ERROR:" not in stderr_at_cleanup[0]
    assert capsys.readouterr().err.splitlines() == ["ERROR: interrupted"]
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


def test_console_main_reraises_with_traceback_printout_off(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``console_main()`` reports the same one line, then re-raises for
    Python to end the process by SIGINT, with nothing more printed."""
    monkeypatch.delenv(PITLOOM_DEBUG_ENV_VAR, raising=False)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(mod_project, "generate_project_sbom", _interrupt)
    project_dir = _make_simple_project(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(project_dir)])

    with pytest.raises(KeyboardInterrupt) as excinfo:
        __main__.console_main()

    assert capsys.readouterr().err.splitlines() == ["ERROR: interrupted"]
    sys.excepthook(excinfo.type, excinfo.value, excinfo.tb)
    assert capsys.readouterr().err == ""


def test_python_m_pitloom_ends_by_sigint(tmp_path: Path) -> None:
    """``python -m pitloom`` interrupted dies by SIGINT, as an uncaught
    ``KeyboardInterrupt`` does, so a shell loop running it stops too; an
    exit status 130 would make bash carry on with the next command."""
    project_dir = _make_simple_project(tmp_path)
    script = tmp_path / "interrupted_loom.py"
    script.write_text(
        "import runpy, sys\n"
        "from pitloom.cli.commands import project\n"
        "def _interrupt(*args, **kwargs):\n"
        "    raise KeyboardInterrupt\n"
        "project.generate_project_sbom = _interrupt\n"
        f"sys.argv = ['loom', 'project', {str(project_dir)!r}]\n"
        "runpy.run_module('pitloom', run_name='__main__')\n",
        encoding="utf-8",
    )
    env = pitloom_subprocess_env()
    env.pop(PITLOOM_DEBUG_ENV_VAR, None)

    result = subprocess.run(  # nosec B603
        [sys.executable, str(script)],
        capture_output=True,
        check=False,
        env=env,
        timeout=120,
    )

    # Windows has no SIGINT death; Python exits STATUS_CONTROL_C_EXIT.
    expected = 0xC000013A if os.name == "nt" else -signal.SIGINT
    assert result.returncode == expected
    assert result.stderr.decode().splitlines() == ["ERROR: interrupted"]
