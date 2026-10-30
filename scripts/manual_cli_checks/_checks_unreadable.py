# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Check 25 of manual-cli-checks.md: a file the system refuses to read and a
directory it refuses to list, in a real project with real permission bits:
one coded line each, no directory of this machine in it, exit 0.

See also: ``_harness.py``; per-surface detail in
``tests/test_unreadable_file_surfaces.py``.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from _harness import DATETIME, CheckSkipped, Context, check, expect, run_ok

_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1"
"""


def _project(root: Path) -> Path:
    for name, text in {
        "pyproject.toml": _PYPROJECT,
        "demo/__init__.py": "x = 1\n",
        "demo/secret.txt": "secret\n",
        "demo/closed/hidden.py": "y = 2\n",
    }.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return root


@check("25", "unreadable file and unlistable dir: one coded line each, no path")
def check_unreadable(ctx: Context) -> None:
    """``loom project`` of a project whose ``demo/secret.txt`` is ``chmod
    000`` and ``demo/closed/`` is ``chmod 000``: exit 0, one ``WARNING:``
    ending ``[file-unreadable]`` and one ending ``[dir-unlistable]``, each
    naming the path project-relative, and no stderr line naming the work
    directory (the OS error's own text would)."""
    if sys.platform == "win32" or os.geteuid() == 0:
        raise CheckSkipped("POSIX permission bits, non-root")
    project = _project(ctx.work / "proj")
    secret, closed = project / "demo" / "secret.txt", project / "demo" / "closed"
    secret.chmod(0)
    closed.chmod(0)
    try:
        result = run_ok(
            "project",
            "--offline",
            "--creation-datetime",
            DATETIME,
            "-o",
            str(ctx.work / "o.json"),
            str(project),
        )
    finally:
        secret.chmod(stat.S_IRUSR | stat.S_IWUSR)
        closed.chmod(stat.S_IRWXU)
    lines = result.stderr_lines
    unread = [line for line in lines if line.endswith(" [file-unreadable]")]
    unlisted = [line for line in lines if line.endswith(" [dir-unlistable]")]
    expect(
        unread
        == [
            "WARNING: FILE=demo/secret.txt: could not read for file "
            "scanning; Permission denied [file-unreadable]"
        ],
        f"file line: {unread}",
    )
    expect(
        [line.partition(";")[0] for line in unlisted]
        == ["WARNING: DIR=demo/closed: could not list for file discovery"],
        f"directory line: {unlisted}",
    )
    leaked = [line for line in lines if str(ctx.work) in line]
    expect(not leaked, f"a line names the work directory: {leaked[:3]}")
    ctx.note("1 file-unreadable, 1 dir-unlistable line; no absolute path")
