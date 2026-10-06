# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Real setuptools builds for tests, offline, in a child process.

A child, not in-process: setuptools emits deprecation warnings that the
test run's ``filterwarnings = error`` would turn into failures.

See also: tests/extract/project/test_setuptools_build_parity.py and
tests/assemble/test_setuptools_licence_surfaces.py, its users.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

#: Variables that would make a child build warn or fail on its own
#: deprecations, whatever Pitloom does.
_SCRUBBED = frozenset({"PYTHONWARNINGS", "SETUPTOOLS_ENFORCE_DEPRECATION"})


def run_build(argv: list[str], cwd: Path | None = None) -> None:
    """Run ``python <argv>`` offline; fail the test with its stderr."""
    env = {k: v for k, v in os.environ.items() if k.upper() not in _SCRUBBED}
    proc = subprocess.run(  # nosec B603
        [sys.executable, *argv],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=180,
        check=False,
    )
    stderr = proc.stderr.decode("utf-8", errors="replace")
    assert proc.returncode == 0, f"build failed:\n{stderr[-1500:]}"


def build_dist(project: Path, out: Path, kind: str) -> Path:
    """*project*'s ``sdist`` or ``wheel`` (*kind*), built from a copy:
    building writes ``*.egg-info`` into the directory it builds."""
    copy = out / f"copy-{kind}"
    shutil.copytree(project, copy)
    run_build(
        ["-m", "build", f"--{kind}", "--no-isolation", "--skip-dependency-check"]
        + ["--outdir", str(out), str(copy)]
    )
    (built,) = out.glob("*.tar.gz" if kind == "sdist" else "*.whl")
    return built
