# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which test files depend on the operating system, not only on the logic.

A file gets the ``platform`` marker when it sits in a directory whose tests
drive the real entry points (``cli``, ``scripts``) or when its source uses
an API whose behaviour differs between Windows, macOS and Linux (see
``OS_USE``). CI runs every test on Linux and, on a pull request, only
``pytest -m platform`` on Windows and macOS; a push to ``main`` runs all.

The rule reads the source, so a new test file is classified without a
hand-kept list. A file may also set ``pytestmark = pytest.mark.platform``.
"""

import re
from functools import cache
from pathlib import Path
from typing import Final

PLATFORM_DIRS: Final[frozenset[str]] = frozenset({"cli", "scripts"})

# What ties a test to the operating system rather than to Pitloom's logic:
# processes, signals, permissions, links, home and temp locations, stream
# encodings, path spelling.
OS_USE: Final[re.Pattern[str]] = re.compile(
    r"subprocess|"
    r"os\.(?:chmod|symlink|mkfifo|getuid|utime|killpg|kill|link|replace|rename)\b|"
    r"\.chmod\(|symlink_to|hardlink_to|signal\.|TextIOWrapper|capfd|"
    r"Path\.home|monkeypatch\.setenv\(\"(?:HOME|USERPROFILE|TMP|TEMP|XDG)|"
    r"sys\.platform|os\.name|posix_only|skipif|PureWindowsPath|ntpath|"
    r"realpath|st_ino|fcntl|msvcrt|normpath|os\.sep|tempfile"
)


@cache
def is_platform_file(path: Path, tests_root: Path) -> bool:
    """Return whether the test file at ``path`` runs on every OS in CI."""
    parts = path.relative_to(tests_root).parts
    if len(parts) > 1 and parts[0] in PLATFORM_DIRS:
        return True
    return OS_USE.search(path.read_text(encoding="utf-8", errors="replace")) is not None
