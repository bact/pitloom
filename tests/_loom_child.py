# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``loom`` in a child process, as a script runs it, and its stderr's coded
lines as a script reads them: for the surface tests of the catalogue.

A child's stderr is held to the strict check of the catalogue
(:mod:`tests._strict_uncoded`): :func:`run_loom` fails on a line that reads
back as ``uncoded`` or ``overlong`` unless a pattern of its *allow* matches
it, and on a pattern that matches no line.

See also: tests/test_model_stub_surfaces.py, tests/test_model_field_surfaces.py
and tests/test_library_unusable_surfaces.py.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
from collections.abc import Sequence
from pathlib import Path

from pitloom.messages import trusted_message
from tests._strict_uncoded import failures, line_finding

SRC = str(Path(__file__).resolve().parents[1] / "src")
#: Runs ``loom`` with the modules of its first argument made unimportable.
_RUN = (
    "import sys\n"
    "for name in filter(None, sys.argv[1].split(',')):\n"
    "    sys.modules[name] = None\n"
    "from pitloom.__main__ import main\n"
    "sys.argv = ['loom', *sys.argv[2:]]\n"
    "sys.exit(main())\n"
)


def run_loom(
    args: list[str],
    cwd: Path,
    block: str = "",
    path: Sequence[Path] = (),
    *,
    allow: Sequence[str] = (),
) -> subprocess.CompletedProcess[bytes]:
    """``loom`` in a child process, *block* (``a,b``) unimportable there and
    *path* before the rest of its import path; its output as bytes, not
    decoded.

    Raises:
        AssertionError: its stderr has a line said without a code that no
            pattern of *allow* matches (:func:`uncoded_failures`), or a
            pattern matches no line.
    """
    env = dict(os.environ)
    entries = [*map(str, path), SRC, env.get("PYTHONPATH")]
    env["PYTHONPATH"] = os.pathsep.join(filter(None, entries))
    done = subprocess.run(  # nosec B603
        [sys.executable, "-c", _RUN, block, *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
        timeout=300,
    )
    failed = uncoded_failures(done.stderr, allow)
    if failed:
        raise AssertionError("loom child, uncoded output: " + "; ".join(failed))
    return done


def uncoded_failures(stderr: bytes, allow: Sequence[str] = ()) -> list[str]:
    """Each failure of the strict check (:func:`tests._strict_uncoded
    .failures`) on the lines of *stderr* (decoded as UTF-8, a carriage
    return dropped) given the patterns *allow*."""
    lines = stderr.decode("utf-8", errors="replace").split("\n")
    found = [line_finding(line.removesuffix("\r")) for line in lines]
    return failures([f for f in found if f is not None], allow)


def coded_lines(stderr: bytes) -> dict[str, str]:
    """Each trusted line of *stderr* (a carriage return dropped) by its text
    and its code, as a script reads them."""
    found = {}
    for raw in stderr.decode("utf-8").split("\n"):
        line = raw.removesuffix("\r")
        message = trusted_message(line)
        if message is not None:
            found[line] = message.code
    return found
