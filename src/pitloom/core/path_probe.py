# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tell a genuinely missing path apart from a present-but-inaccessible one.

``Path.exists()``/``Path.is_file()`` cannot do this portably: on Python
3.10-3.13 they raise ``PermissionError``, on 3.14 they return ``False``
for it -- the same answer as for a missing path. Shared by fragment
presence checks (:mod:`pitloom.assemble.spdx3.fragments`,
``loom fragment list``) and the wheel file scan
(:mod:`pitloom.core._models_wheel`), so all three classify a ``stat()``
failure identically.

:data:`UNREADABLE_FILE_WARNING` is the one wording every per-file read
failure is reported with, so the ``FILE=`` warnings stay grep-able as one
group.
"""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

__all__ = [
    "STAT_MISSING_ERRNOS",
    "STAT_MISSING_WINERRORS",
    "UNREADABLE_FILE_WARNING",
    "is_missing_errno",
    "is_regular_file",
]

#: errno values Path.exists()/is_file() themselves treat as "this path
#: doesn't apply" rather than a real failure (POSIX).
STAT_MISSING_ERRNOS = frozenset({errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP})
#: Windows counterparts of the same errno set, per CPython's
#: pathlib._ignore_error().
STAT_MISSING_WINERRORS = frozenset({21, 123, 1921})

#: ``log.warning()`` format for a file that exists but cannot be read.
#: Arguments: the stable ``FILE=`` path, what the read was for (e.g.
#: ``"for file scanning"``), the exception.
UNREADABLE_FILE_WARNING = "FILE=%s: could not read %s; %s"


def is_missing_errno(exc: OSError) -> bool:
    """True when *exc* (raised by a ``stat()``/``exists()``-style call)
    represents a genuinely missing path, using the same errno (POSIX) or
    ``winerror`` (Windows) classification ``Path.exists()`` uses
    internally -- any other ``OSError`` (e.g. permission denied) means the
    path is present but inaccessible, not missing.

    Checks both unconditionally (``or``, not "prefer winerror when set"):
    a real Windows ``FileNotFoundError`` carries *both* ``errno=ENOENT``
    and a ``winerror`` that ``STAT_MISSING_WINERRORS`` doesn't cover
    (winerror 2/3, not 21/123/1921) -- short-circuiting on ``winerror is
    not None`` would misclassify that as "not missing". Matches CPython's
    own ``pathlib._ignore_error()``:
    ``errno in _IGNORED_ERRNOS or winerror in _IGNORED_WINERRORS``.
    """
    return (
        exc.errno in STAT_MISSING_ERRNOS
        or getattr(exc, "winerror", None) in STAT_MISSING_WINERRORS
    )


def is_regular_file(path: Path) -> bool:
    """``Path.is_file()``, except a genuine access failure raises.

    ``False`` for a missing path (per :func:`is_missing_errno`) or a
    non-regular one; the ``stat()`` ``OSError`` otherwise (e.g.
    ``PermissionError`` for a file under a directory without search
    permission), on every Python version.
    """
    try:
        mode = os.stat(path).st_mode
    except OSError as exc:
        if is_missing_errno(exc):
            return False
        raise
    return stat.S_ISREG(mode)
