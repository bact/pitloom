# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``--build-timeout`` checks of manual-cli-checks.md: a real
``loom project --allow-build --no-build-isolation`` over in-tree PEP 517
backends (``backend-path = ["."]``, ``requires = []``: no network).

See also: ``_harness.py``, ``_checks_core.py``.
"""

from __future__ import annotations

import os
import signal
import subprocess  # nosec B404
import sys
import time
from pathlib import Path

from _harness import (
    DATETIME,
    CheckFailed,
    CheckSkipped,
    Context,
    Result,
    check,
    child_env,
    expect,
    expect_tagged,
    loom_argv,
    run_loom,
)

_WRITE_PID = (
    "import os\n"
    "def _write_pid(name, pid=None):\n"
    "    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)\n"
    "    with open(path + '.tmp', 'w') as f:\n"
    "        f.write(str(pid or os.getpid()))\n"
    "    os.replace(path + '.tmp', path)\n"
)
_SIG = (
    "def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):\n"
)
_BACKENDS = {
    "slow": _SIG
    + "    import time\n    _write_pid('backend.pid')\n    time.sleep(300)\n",
    "stdin": _SIG + "    input()\n",
    # Builds a real wheel, leaving a background process running.
    "leftover": (
        "import subprocess, sys, zipfile\n"
        + _SIG
        + "    child = subprocess.Popen([sys.executable, '-c',"
        " 'import time; time.sleep(300)'])\n"
        "    _write_pid('leftover.pid', child.pid)\n"
        "    name = 'demo-0.1-py3-none-any.whl'\n"
        "    with zipfile.ZipFile(os.path.join(wheel_directory, name), 'w') as zf:\n"
        "        zf.writestr('demo/__init__.py', '')\n"
        "        zf.writestr('demo-0.1.dist-info/METADATA',"
        " 'Metadata-Version: 2.1\\nName: demo\\nVersion: 0.1\\n')\n"
        "        zf.writestr('demo-0.1.dist-info/WHEEL', 'Wheel-Version: 1.0\\n"
        "Generator: test\\nRoot-Is-Purelib: true\\nTag: py3-none-any\\n')\n"
        "        zf.writestr('demo-0.1.dist-info/RECORD', '')\n"
        "    return name\n"
    ),
}
_INVALID_TIMEOUTS = ("0", "1.5h", "500ms", "1H", "604801")


def _backend_project(ctx: Context, kind: str) -> tuple[Path, Path]:
    """A project built by the *kind* backend, and an empty dir to serve
    as the build's ``TMPDIR`` (so leftovers are visible)."""
    project = ctx.work / f"proj-{kind}"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (project / f"{kind}_backend.py").write_text(
        _WRITE_PID + _BACKENDS[kind], encoding="utf-8"
    )
    (project / "pyproject.toml").write_text(
        f'[project]\nname = "demo"\nversion = "0.1"\n\n[build-system]\n'
        f'requires = []\nbuild-backend = "{kind}_backend"\nbackend-path = ["."]\n',
        encoding="utf-8",
    )
    tmp = ctx.work / f"tmp-{kind}"
    tmp.mkdir()
    return project, tmp


def _build_args(project: Path, out: Path, *extra: str) -> list[str]:
    return [
        "project",
        str(project),
        "-o",
        str(out),
        "--allow-build",
        "--no-build-isolation",
        "--creation-datetime",
        DATETIME,
        *extra,
    ]


def _tmp_env(tmp: Path) -> dict[str, str]:
    return child_env(TMPDIR=str(tmp), TEMP=str(tmp), TMP=str(tmp))


def _pid_gone(pid: int, limit: float = 10.0) -> bool:
    """POSIX: *pid* no longer runs (a zombie counts as gone)."""
    deadline = time.monotonic() + limit
    while True:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return True
        stat = Path(f"/proc/{pid}/stat")
        if (
            stat.exists()
            and stat.read_text(encoding="ascii").rsplit(")", 1)[1].split()[0] == "Z"
        ):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)


def _expect_clean(project: Path, tmp: Path, pid_file: str) -> None:
    """The backend process is gone and the build left nothing in *tmp*
    (POSIX only: Windows may keep a just-killed build's temp dir)."""
    if sys.platform == "win32":
        return
    pid = int((project / pid_file).read_text(encoding="ascii"))
    expect(_pid_gone(pid), f"process {pid} ({pid_file}) still running")
    left = sorted(p.name for p in tmp.iterdir())
    expect(not left, f"left in the build's TMPDIR: {left}")


@check("B1", "--build-timeout: slow build killed, falls back, cleans up")
def check_timeout(ctx: Context) -> None:
    project, tmp = _backend_project(ctx, "slow")
    result = run_loom(
        *_build_args(project, ctx.work / "out.json", "--build-timeout", "5"),
        env=_tmp_env(tmp),
        timeout=180,
    )
    expect(result.returncode == 0, result.describe())
    expect_tagged(result)
    timed_out = [ln for ln in result.stderr.splitlines() if "[build-timeout]" in ln]
    expect(len(timed_out) == 1, result.describe())
    expect("timed out after 5 seconds" in timed_out[0], result.describe())
    # The build ran into its 5 s deadline, and was stopped soon after it.
    expect(5 <= result.elapsed < 60, f"took {result.elapsed:.1f}s for a 5s timeout")
    _expect_clean(project, tmp, "backend.pid")
    ctx.note(f"returned in {result.elapsed:.1f}s")


def _signal_mid_build(ctx: Context, sig: signal.Signals) -> tuple[int, str]:
    if sys.platform == "win32":
        raise CheckSkipped("POSIX signals")
    project, tmp = _backend_project(ctx, "slow")
    pid_file = project / "backend.pid"
    with subprocess.Popen(  # nosec B603
        loom_argv(*_build_args(project, ctx.work / "out.json")),
        env=_tmp_env(tmp),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    ) as proc:
        try:
            deadline = time.monotonic() + 120
            while not pid_file.exists():
                if proc.poll() is not None or time.monotonic() > deadline:
                    raise CheckFailed("the build never started")
                time.sleep(0.1)
            proc.send_signal(sig)
            _, err = proc.communicate(timeout=60)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    _expect_clean(project, tmp, "backend.pid")
    return proc.returncode, err.decode("utf-8", "replace")


@check("B2", "SIGTERM mid-build: exit 143, build tree killed, cleans up")
def check_sigterm(ctx: Context) -> None:
    code, err = _signal_mid_build(ctx, signal.SIGTERM)
    expect(code in (-signal.SIGTERM, 128 + signal.SIGTERM), f"exit {code}\n{err}")
    expect("received SIGTERM during the build" in err, err)
    expect("[interrupted]" in err, err)


@check("B3", "SIGINT (Ctrl-C) mid-build: exit 130, build tree killed, cleans up")
def check_sigint(ctx: Context) -> None:
    code, err = _signal_mid_build(ctx, signal.SIGINT)
    expect(code in (-signal.SIGINT, 128 + signal.SIGINT), f"exit {code}\n{err}")


def _run_with_open_stdin(ctx: Context, args: list[str], tmp: Path) -> Result:
    """``loom *args`` with its stdin an open pipe never written to, as in
    a terminal: only Pitloom closing the build's stdin gives it EOF."""
    out, err = ctx.work / "stdout.txt", ctx.work / "stderr.txt"
    start = time.monotonic()
    with (
        out.open("wb") as out_file,
        err.open("wb") as err_file,
        subprocess.Popen(  # nosec B603
            loom_argv(*args),
            env=_tmp_env(tmp),
            stdin=subprocess.PIPE,
            stdout=out_file,
            stderr=err_file,
        ) as proc,
    ):
        try:
            returncode = proc.wait(timeout=300)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    return Result(
        args,
        returncode,
        out.read_text(encoding="utf-8", errors="replace"),
        err.read_text(encoding="utf-8", errors="replace"),
        time.monotonic() - start,
    )


@check("B4", "a build reading stdin fails fast, not after the timeout")
def check_stdin(ctx: Context) -> None:
    project, tmp = _backend_project(ctx, "stdin")
    # Bounded: a build that sees the open stdin hangs until the timeout.
    args = _build_args(project, ctx.work / "out.json", "--build-timeout", "60")
    result = _run_with_open_stdin(ctx, args, tmp)
    expect(result.returncode == 0, result.describe())
    expect_tagged(result)
    expect(result.elapsed < 120, f"took {result.elapsed:.0f}s")
    expect("[build-failed]" in result.stderr, result.describe())
    expect("[build-timeout]" not in result.stderr, result.describe())


@check("B5", "processes a build leaves running: killed, INFO: once, deterministic")
def check_leftover(ctx: Context) -> None:
    if sys.platform == "win32":
        raise CheckSkipped("POSIX process groups")
    project, tmp = _backend_project(ctx, "leftover")
    outputs = []
    for run in ("a", "b"):
        out = ctx.work / f"{run}.json"
        result = run_loom(*_build_args(project, out), env=_tmp_env(tmp), timeout=300)
        expect(result.returncode == 0, result.describe())
        expect_tagged(result)
        left = [
            ln
            for ln in result.stderr.splitlines()
            if ln.startswith("INFO: Build: ") and "[build-processes-unsafe]" in ln
        ]
        expect(len(left) == 1, result.describe())
        _expect_clean(project, tmp, "leftover.pid")
        outputs.append(out.read_bytes())
    expect(outputs[0] == outputs[1], "the two SBOMs differ")


@check("B6", "invalid --build-timeout values exit 2 on every subcommand")
def check_invalid_values(ctx: Context) -> None:
    targets = {
        "project": [str(ctx.work)],
        "generate": [str(ctx.work)],
        "embed-wheel": [str(ctx.work / "x.whl")],
    }
    for sub, target in targets.items():
        for value in _INVALID_TIMEOUTS:
            result = run_loom(sub, *target, "--allow-build", f"--build-timeout={value}")
            expect(result.returncode == 2, f"{sub} {value!r}: {result.describe()}")


@check("B7", "--build-timeout without --allow-build: one WARNING:, no build")
def check_stray_flag(ctx: Context) -> None:
    project, tmp = _backend_project(ctx, "slow")
    result = run_loom(
        "project",
        str(project),
        "-o",
        str(ctx.work / "out.json"),
        "--build-timeout",
        "5",
        env=_tmp_env(tmp),
    )
    expect(result.returncode == 0, result.describe())
    expect_tagged(result)
    warning = "--build-timeout has no effect without --allow-build"
    expect(result.stderr.count(warning) == 1, result.describe())
    expect(not (project / "backend.pid").exists(), "a build ran")
