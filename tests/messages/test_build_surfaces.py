# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``--allow-build`` on every surface that builds: ``loom project`` and
``loom generate`` (a child process: the ``build-failed`` line, then the
file-discovery fallback line; the ``build-timeout`` line; a SIGTERM and a
Ctrl-C mid-build, the ``interrupted`` line) and the library
(``generate_project_sbom``: the same codes on the log records). The exit
status is as it was, standard output holds data only, and an SBOM is the same
bytes on every run. The builds are in-tree PEP 517 backends, with no build
isolation, so nothing is fetched.

See also: tests/core/models_wheel/test_models_wheel_build_codes.py (each line
of a build, below the command line), tests/cli/test_cli_build_timeout_process.py
(the timeout and the cleanup) and tests/messages/test_build.py (the lines).
"""

from __future__ import annotations

import json
import logging
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.core.build_options import BuildOptions
from pitloom.logging_config import CODE_ATTR
from tests._loom_child import coded_lines, run_loom
from tests._pid import wait_pid_gone
from tests.build_and_read_shared import pitloom_subprocess_env

# pylint: disable-next=C0412
from tests.core.models_wheel.test_models_wheel_build_subprocess_e2e import (
    _FAST_BACKEND,
    _SLOW_BACKEND,
)

pytestmark = pytest.mark.platform  # child processes, signals, stdout bytes

#: Read as one short-circuited constant, never a skipif made of a name
#: Windows lacks.
_POSIX = sys.platform != "win32"
_AT = ["--creation-datetime", "2026-01-01T00:00:00Z"]
_BUILD = ["--allow-build", "--no-build-isolation"]
_TAGS = ("ERROR: ", "WARNING: ", "INFO: ")
_FAILING = textwrap.dedent(
    """
    def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
        raise RuntimeError("the backend gave up")
    """
)
_PYPROJECT = textwrap.dedent(
    """
    [project]
    name = "demo"
    version = "0.1"

    [build-system]
    requires = []
    build-backend = "{backend}"
    backend-path = ["."]
    """
)


def _project(root: Path, backend: str, source: str) -> Path:
    """A project built by the in-tree backend *backend* (*source*)."""
    project = root / "proj"
    project.mkdir()
    (project / f"{backend}.py").write_text(source, encoding="utf-8")
    (project / "demo").mkdir()
    (project / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        _PYPROJECT.format(backend=backend), encoding="utf-8"
    )
    return project


@pytest.fixture(name="failing")
def _failing(tmp_path: Path) -> Path:
    return _project(tmp_path, "failing_backend", _FAILING)


def _codes(stderr: bytes) -> list[str]:
    """The code of each trusted line of *stderr*, in order."""
    return list(coded_lines(stderr).values())


def _tagged(stderr: bytes) -> list[str]:
    """Each line of *stderr*, each starting with exactly one level tag."""
    lines = [ln for ln in stderr.decode("utf-8").splitlines() if ln.strip()]
    assert all(ln.startswith(_TAGS) for ln in lines), lines
    assert not any(ln[ln.index(": ") + 2 :].startswith(_TAGS) for ln in lines)
    return lines


# -- the command line ----------------------------------------------------------


@pytest.mark.parametrize("command", ["project", "generate"])
@pytest.mark.parametrize("output", ["file", "stdout"])
def test_a_failed_build_is_a_coded_line_then_the_fallback_line(
    tmp_path: Path, failing: Path, command: str, output: str
) -> None:
    out = tmp_path / "out.spdx3.json" if output == "file" else Path("-")
    result = run_loom([command, str(failing), *_BUILD, *_AT, "-o", str(out)], tmp_path)
    assert result.returncode == 0, result.stderr  # a failed build is no failure
    lines = _tagged(result.stderr)
    codes = coded_lines(result.stderr)
    assert list(codes.values()) == [
        "build-code-unsafe",
        "build-failed",
        "file-discovery-needs-build",
    ], lines
    (failed,) = [ln for ln, code in codes.items() if code == "build-failed"]
    assert failed.startswith("WARNING: Build: DIR=")
    assert ": the build exited with code 1; last output: " in failed
    assert lines.index(failed) == lines.index(next(iter(codes))) + 1
    # Data only: the SBOM, or the KEY=VALUE of where it went.
    if output == "stdout":
        assert json.loads(result.stdout)["@graph"]
    else:
        (data,) = result.stdout.decode("utf-8").splitlines()
        assert data.startswith("PITLOOM_SBOM_OUTPUT_PATH=")
        assert json.loads(out.read_bytes())["@graph"]


def test_a_build_that_works_says_only_what_it_runs(tmp_path: Path) -> None:
    """The other side: no ``build-failed``, no fallback line."""
    project = _project(tmp_path, "fast_backend", _FAST_BACKEND)
    result = run_loom(
        ["project", str(project), *_BUILD, *_AT, "-o", str(tmp_path / "o.json")],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert _codes(result.stderr) == ["build-code-unsafe"]
    assert len(_tagged(result.stderr)) == 1


def test_a_build_past_its_time_is_a_coded_line_and_the_run_goes_on(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path, "slow_backend", _SLOW_BACKEND)
    result = run_loom(
        ["project", str(project), *_BUILD, "--build-timeout", "1", *_AT]
        + ["-o", str(tmp_path / "o.json")],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr  # the exit status as it was
    codes = coded_lines(result.stderr)
    # Windows may keep a just-killed build's directory (temp-dir-unwritable).
    assert [c for c in codes.values() if c != "temp-dir-unwritable"] == [
        "build-code-unsafe",
        "build-timeout",
        "file-discovery-needs-build",
    ]
    said = {code: ln for ln, code in codes.items()}
    # One second, singular, in both lines that state the limit.
    assert "build for up to 1 second (--build-timeout), " in said["build-code-unsafe"]
    line = said["build-timeout"]
    assert "the build timed out after 1 second (--build-timeout); " in line
    assert line.endswith(" [build-timeout]")
    _tagged(result.stderr)


# -- a signal mid-build --------------------------------------------------------


def _signalled(root: Path, sig: int) -> tuple[subprocess.CompletedProcess[bytes], Path]:
    """Run ``loom project --allow-build`` on a build that never ends, send
    *sig* once its backend runs, and wait for the end."""
    project = _project(root, "slow_backend", _SLOW_BACKEND)
    env = pitloom_subprocess_env()
    env.pop("PITLOOM_DEBUG", None)
    command = [sys.executable, "-m", "pitloom", "project", str(project), *_BUILD]
    command += ["--build-timeout", "120", "-o", str(root / "o.json")]
    with subprocess.Popen(  # nosec B603
        command,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as loom:
        try:
            deadline = time.monotonic() + 120
            while not (project / "backend.pid").exists():
                assert time.monotonic() < deadline, "the backend never started"
                time.sleep(0.1)
            loom.send_signal(sig)
            out, err = loom.communicate(timeout=120)
        finally:
            if loom.poll() is None:
                loom.kill()
                loom.communicate()
    done = subprocess.CompletedProcess(command, loom.returncode, out, err)
    return done, project / "backend.pid"


@pytest.mark.skipif(not _POSIX, reason="SIGTERM and SIGINT end a POSIX process")
@pytest.mark.parametrize(
    ("name", "line"),
    [
        (
            "SIGTERM",
            "WARNING: Build: received SIGTERM during the build; "
            "exiting after cleanup [interrupted]",
        ),
        ("SIGINT", "ERROR: loom project: interrupted [interrupted]"),
    ],
    ids=["sigterm", "ctrl-c"],
)
def test_a_signal_mid_build_is_one_coded_line_and_the_process_dies_by_it(
    tmp_path: Path, name: str, line: str
) -> None:
    sig = signal.Signals[name]
    result, pid_file = _signalled(tmp_path, sig)
    # As it was: the process ends by the signal itself (a shell sees 143, 130).
    assert result.returncode == -sig, result.stderr
    lines = _tagged(result.stderr)
    assert lines[-1] == line and result.stdout == b""
    assert coded_lines(result.stderr)[line] == "interrupted"
    assert _codes(result.stderr).count("interrupted") == 1
    assert "build-failed" not in _codes(result.stderr)
    assert wait_pid_gone(int(pid_file.read_text(encoding="ascii")))
    assert not (tmp_path / "o.json").exists()  # no SBOM written


# -- the library ---------------------------------------------------------------


def _records(caplog: pytest.LogCaptureFixture) -> list[tuple[str, str]]:
    """The code and level of each coded record, in order."""
    return [
        (getattr(r, CODE_ATTR), r.levelname)
        for r in caplog.records
        if getattr(r, CODE_ATTR, None) is not None
    ]


def test_the_library_says_the_same_codes_on_the_log(
    failing: Path, caplog: pytest.LogCaptureFixture
) -> None:
    options = BuildOptions(allow=True, no_isolation=True)
    with caplog.at_level(logging.INFO):
        sbom = generate_project_sbom(failing, build_options=options)
    assert json.loads(sbom)["@graph"]
    assert _records(caplog) == [
        ("build-code-unsafe", "WARNING"),
        ("build-failed", "WARNING"),
        ("file-discovery-needs-build", "WARNING"),
    ]
    (failed,) = [r for r in caplog.records if getattr(r, CODE_ATTR) == "build-failed"]
    assert failed.getMessage().startswith("Build: DIR=")
    assert "the build exited with code 1; last output: " in failed.getMessage()


def test_the_library_says_a_timeout_on_the_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    project = _project(tmp_path, "slow_backend", _SLOW_BACKEND)
    options = BuildOptions(allow=True, no_isolation=True, timeout=1)
    with caplog.at_level(logging.INFO):
        generate_project_sbom(project, build_options=options)
    seen = [code for code, _ in _records(caplog) if code != "temp-dir-unwritable"]
    assert seen == [
        "build-code-unsafe",
        "build-timeout",
        "file-discovery-needs-build",
    ]
    said = {getattr(r, CODE_ATTR): r.getMessage() for r in caplog.records}
    # A library call names the library's limit.
    unsafe = said["build-code-unsafe"]
    assert "BuildOptions.allow runs a PEP 517 build for up to 1 second " in unsafe
    assert "(BuildOptions.timeout), " in unsafe
    assert "timed out after 1 second (BuildOptions.timeout); " in said["build-timeout"]


def test_the_library_says_nothing_of_a_build_it_was_not_asked_for(
    failing: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        generate_project_sbom(failing)
    assert "build-failed" not in [code for code, _ in _records(caplog)]
    assert "Build: DIR=" not in caplog.text


# -- the SBOM ------------------------------------------------------------------


def _sbom(tmp_path: Path, project: Path, *args: str) -> bytes:
    result = run_loom(["project", str(project), *args, *_AT, "-o", "-"], tmp_path)
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize("args", [_BUILD, []], ids=["failed-build", "no-build"])
def test_the_sbom_is_the_same_bytes_on_every_run(
    tmp_path: Path, failing: Path, args: list[str]
) -> None:
    first = _sbom(tmp_path, failing, *args)
    second = _sbom(tmp_path, failing, *args)
    assert first == second and first.endswith(b"\n")
    # Nothing of a build's temporary directories or its text is in it.
    for leaked in (b"plb-", b"pitloom-build-and-read", b"the build exited"):
        assert leaked not in first
