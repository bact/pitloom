# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``scripts/message_inventory/_scope.py``, rule R-a: an ``OSError`` raised
from the system's own errno and description (``PermissionError(exc.errno,
exc.strerror, path)``) is the detail of the line its caller says, out of
scope; an ``OSError`` given a text of Pitloom's stays counted.

Each case is a line of :data:`SOURCE` ending in ``# in: <id>`` (the ratchet
counts it) or ``# out: <id>`` (it does not).

See also: test_inventory.py (the other scope rules).
"""

from __future__ import annotations

import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SOURCE = """\
import errno
import os


def write(path, exc):
    raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), path)  # out: errno
    raise PermissionError(exc.errno, exc.strerror, str(path))  # out: rebuilt
    raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))  # out: no-path
    raise FileNotFoundError(exc.errno, exc.strerror)  # out: subclass
    raise PermissionError(errno.EACCES, "no access", str(path))  # in: own-text
    raise PermissionError("no access here")  # in: text-only
    raise PermissionError(errno.EACCES)  # in: errno-only
    raise PermissionError(13, os.strerror(13), path)  # in: literal-errno
    raise PermissionError(exc.code, exc.strerror)  # in: not-errno
    raise PermissionError(errno.EACCES, exc.reason)  # in: not-strerror
    raise ValueError(errno.EACCES, os.strerror(errno.EACCES))  # in: not-os-error
    raise RuntimeError(exc.errno, exc.strerror)  # in: runtime-error
    raise OSError(errno.EIO, os.strerror(errno.EIO) + loggable(path))  # in: plus-text
    raise OSError(errno.EIO, "no: " + os.strerror(errno.EIO))  # in: text-plus
    raise PermissionError(exc.errno, f"{exc.strerror}!")  # in: strerror-in-f-string
    raise PermissionError(exc.errno, exc.strerror, f"in {path}")  # in: path-text
    raise PermissionError(exc.errno, exc.strerror, loggable(path))  # in: path-call
    raise PermissionError(exc.errno, exc.strerror, str(path, "x"))  # in: str-two-args
    raise PermissionError(exc.errno, exc.strerror, path, 5)  # in: extra-arg
    raise PermissionError(exc.errno, exc.strerror, path, other)  # in: two-paths
    raise OSError(errno.EIO, shutil.strerror(errno.EIO))  # in: other-strerror
    raise OSError(errno.EIO, os.strerror(errno.EIO, 1))  # in: strerror-two-args
    raise PermissionError(errno.eacces, os.strerror(13))  # in: lower-errno
    raise PermissionError(a.b.errno, exc.strerror)  # in: nested-errno
    raise PermissionError(exc.errno, a.b.strerror)  # in: nested-strerror
    raise PermissionError("errno.EACCES", os.strerror(13))  # in: literal-text
"""

_MARK = re.compile(r"# (in|out): (\S+)$")
CASES = [
    (n, mark[0] == "in", mark[1])
    for n, line in enumerate(SOURCE.splitlines(), start=1)
    for mark in _MARK.findall(line)
]


@pytest.fixture(name="records", scope="module")
def records_fixture(
    mi: ModuleType, tmp_path_factory: pytest.TempPathFactory
) -> list[dict[str, Any]]:
    """The sites of :data:`SOURCE` as ``src/pitloom/writer.py``."""
    root = tmp_path_factory.mktemp("os-errors")
    package = root / "src" / "pitloom"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    (package / "writer.py").write_bytes(SOURCE.encode("utf-8"))
    return mi.inventory(Path(root))  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("line", "scoped"),
    [(n, scoped) for n, scoped, _ in CASES],
    ids=[case_id for _, _, case_id in CASES],
)
def test_an_os_error_of_the_systems_words_is_out_of_scope(
    mi: ModuleType, records: list[dict[str, Any]], line: int, scoped: bool
) -> None:
    (site,) = [r for r in records if r["line"] == line]
    assert mi.in_scope(site) is scoped
    assert (mi.reach(site) == "detail") is not scoped
