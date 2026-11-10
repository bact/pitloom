# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Whether a process is gone, for tests that kill a child tree."""

import os
import subprocess
import sys
import time
from pathlib import Path


def pid_gone(pid: int) -> bool:
    if sys.platform == "win32":  # os.kill() on Windows terminates, not probes
        return _windows_pid_gone(pid)
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return True
    # Linux: a killed orphan answers kill(pid, 0) until init reaps it.
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except OSError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] == "Z"


def _windows_pid_gone(pid: int) -> bool:
    """Whether no running process has *pid*, per ``tasklist`` (CSV, no
    header: one quoted row per match, none when it has exited)."""
    tasklist = Path(
        os.environ.get("SystemRoot", r"C:\Windows"), "System32", "tasklist.exe"
    )
    rows = subprocess.run(
        [str(tasklist), "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout
    return f'"{pid}"' not in rows


def wait_pid_gone(pid: int, limit: float = 10.0) -> bool:
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        if pid_gone(pid):
            return True
        time.sleep(0.1)
    return pid_gone(pid)
