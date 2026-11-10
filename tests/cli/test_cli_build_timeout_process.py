# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``loom project --allow-build --build-timeout`` as a real process: the
entry point, real stderr and exit code, over a real ``python -m build``
of an in-tree backend that never finishes (no network).

See also: :mod:`tests.core.models_wheel.test_models_wheel_build_subprocess_e2e`
(the build subprocess and its kill path, below the CLI) and
:mod:`tests.cli.test_cli_build_timeout` (in-process flag parsing).
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from tests._pid import wait_pid_gone
from tests.build_and_read_shared import pitloom_subprocess_env
from tests.core.models_wheel.test_models_wheel_build_subprocess_e2e import (
    _SLOW_BACKEND,
)

_TAGS = ("ERROR: ", "WARNING: ", "INFO: ")


def test_loom_project_build_timeout_falls_back_and_cleans_up(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "slow_backend.py").write_text(_SLOW_BACKEND, encoding="utf-8")
    (project / "demo").mkdir()
    (project / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "demo"
            version = "0.1"

            [build-system]
            requires = []
            build-backend = "slow_backend"
            backend-path = ["."]
            """
        ),
        encoding="utf-8",
    )
    sys_tmp = tmp_path / "sys-tmp"
    sys_tmp.mkdir()
    out = tmp_path / "out.spdx3.json"
    env = pitloom_subprocess_env(
        TMPDIR=str(sys_tmp), TEMP=str(sys_tmp), TMP=str(sys_tmp)
    )
    # DEBUG lines are untagged by design; an exported PITLOOM_DEBUG must
    # not reach the child.
    env.pop("PITLOOM_DEBUG", None)

    result = subprocess.run(  # nosec B603
        [
            sys.executable,
            "-m",
            "pitloom",
            "project",
            str(project),
            "--allow-build",
            "--no-build-isolation",
            "--build-timeout",
            # Generous: the backend must start (interpreter + build) before
            # it, on a slow CI runner too.
            "20",
            "-o",
            str(out),
        ],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=120,
        check=False,
    )

    stderr = result.stderr.decode("utf-8", errors="replace")
    assert result.returncode == 0, stderr
    lines = [line for line in stderr.splitlines() if line.strip()]
    # Every stderr line carries exactly one level tag (AGENTS.md "CLI output").
    assert all(line.startswith(_TAGS) for line in lines), lines
    assert sum("timed out after 20s" in line for line in lines) == 1, lines
    assert json.loads(out.read_bytes())["@graph"]
    # The build's own temp dir was redirected into Pitloom's work dir...
    build_tmp = Path((project / "tempdir.txt").read_text(encoding="utf-8"))
    assert build_tmp.name == "t", build_tmp
    assert build_tmp.parent.name.startswith("plb-"), build_tmp
    assert build_tmp.resolve().parent.parent == sys_tmp.resolve()
    pid = int((project / "backend.pid").read_text(encoding="ascii"))
    if sys.platform != "win32":  # os.kill() on Windows terminates, not probes
        assert wait_pid_gone(pid), f"backend process {pid} survived the timeout"
        # ...and nothing at all is left there (Windows may keep a
        # just-killed build's temp dir, as documented).
        assert not list(sys_tmp.iterdir())
