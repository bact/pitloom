# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Make one project file unreadable, portably or for real.

``deny`` modes, shared by the file-scan unit tests and the cross-surface
test so both exercise the same failures:

- ``"open"``: opening the file raises ``PermissionError`` (monkeypatched,
  every platform) -- as for a ``chmod 000`` file.
- ``"stat"``: ``stat()`` on it raises ``PermissionError`` (monkeypatched,
  every platform) -- as for a file under a directory without search
  permission, where ``Path.is_file()`` raises on Python 3.10-3.13 and
  returns ``False`` on 3.14.
- ``"chmod-file"``/``"chmod-dir"``: the real POSIX permission bits; only
  meaningful when :data:`POSIX_NON_ROOT` (root bypasses them).

See also: tests/core/models_wheel/test_models_wheel_unreadable.py,
tests/test_unreadable_file_surfaces.py.
"""

from __future__ import annotations

import errno
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

# Short-circuited: os.geteuid does not exist on Windows.
POSIX_NON_ROOT = sys.platform != "win32" and os.geteuid() != 0

PORTABLE_MODES = ("open", "stat")
POSIX_MODES = ("chmod-file", "chmod-dir")

_POSIX_ONLY = pytest.mark.skipif(
    not POSIX_NON_ROOT, reason="needs POSIX permissions, non-root"
)

#: pytest params for every mode, the POSIX ones skipped where meaningless.
ALL_MODES = [
    *PORTABLE_MODES,
    *(pytest.param(mode, marks=_POSIX_ONLY) for mode in POSIX_MODES),
]
#: The modes where stat() itself fails.
STAT_MODES = ["stat", pytest.param("chmod-dir", marks=_POSIX_ONLY)]


def _denied(path: str | os.PathLike[str]) -> PermissionError:
    return PermissionError(errno.EACCES, os.strerror(errno.EACCES), os.fspath(path))


@contextmanager
def deny(target: Path, mode: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make *target* (an existing file) unreadable per *mode* for the block.

    Every mode is undone when the block exits, not at test teardown.
    """
    # abspath, not resolve()/realpath(): no syscalls, so no recursion into
    # the patched stat. tmp_path and get_wheel_files() paths are resolved.
    denied_path = os.path.abspath(target)
    if mode == "open":
        real_open = Path.open

        def _open(self: Path, *args: Any, **kwargs: Any) -> Any:
            if os.path.abspath(self) == denied_path:
                raise _denied(self)
            return real_open(self, *args, **kwargs)

        def _read_bytes(self: Path) -> bytes:
            with _open(self, "rb") as handle:
                return bytes(handle.read())

        with monkeypatch.context() as patch:
            patch.setattr(Path, "open", _open)
            # read_bytes() need not go through Path.open on every version.
            patch.setattr(Path, "read_bytes", _read_bytes)
            yield
        return
    if mode == "stat":
        real_stat = os.stat

        def _stat(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
            if (
                isinstance(path, (str, os.PathLike))
                and os.path.abspath(path) == denied_path
            ):
                raise _denied(path)
            return real_stat(path, *args, **kwargs)

        # Python 3.10's pathlib binds os.stat at import: Path.stat() and
        # Path.is_file() do not see this patch there; os.stat() callers do.
        with monkeypatch.context() as patch:
            patch.setattr(os, "stat", _stat)
            yield
        return
    locked = target if mode == "chmod-file" else target.parent
    original = locked.stat().st_mode
    # A directory keeps read (listable) but loses search: stat() of an
    # entry fails, discovery still sees the name.
    locked.chmod(0 if mode == "chmod-file" else 0o644)
    try:
        yield
    finally:
        locked.chmod(original)
