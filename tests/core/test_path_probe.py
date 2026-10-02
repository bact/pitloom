# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.path_probe`.

See also: tests/_unreadable.py, tests/core/models_wheel/test_models_wheel_unreadable.py.
"""

from __future__ import annotations

import errno
from pathlib import Path

import pytest

from pitloom.core.path_probe import is_missing_errno, is_regular_file
from tests._unreadable import ALL_MODES, STAT_MODES, deny


class TestIsMissingErrno:
    """is_missing_errno() must classify both POSIX errno and Windows
    winerror the way Path.exists()/is_file() do internally, so a stat()
    failure is never misreported as "missing" on either platform."""

    def test_posix_missing_errno_is_missing(self) -> None:
        exc = FileNotFoundError(errno.ENOENT, "No such file or directory")
        assert is_missing_errno(exc) is True

    def test_posix_permission_errno_is_not_missing(self) -> None:
        exc = PermissionError(errno.EACCES, "Permission denied")
        assert is_missing_errno(exc) is False

    def test_windows_missing_winerror_is_missing(self) -> None:
        """Windows reports "not found" via winerror, not errno -- a real
        FileNotFoundError raised on Windows carries winerror 2/3/21
        depending on cause; 21 (ERROR_NOT_READY, used for a bad drive/UNC
        path) is one of pathlib's own recognised "missing" codes."""
        exc = OSError("The device is not ready")
        exc.winerror = 21  # type: ignore[attr-defined]
        assert is_missing_errno(exc) is True

    def test_windows_non_missing_winerror_is_not_missing(self) -> None:
        exc = OSError("Access is denied")
        exc.winerror = 5  # type: ignore[attr-defined]
        assert is_missing_errno(exc) is False

    def test_windows_real_file_not_found_has_both_errno_and_winerror(self) -> None:
        """A real Windows FileNotFoundError carries BOTH errno=ENOENT and a
        winerror (typically 2/3, ERROR_FILE_NOT_FOUND/ERROR_PATH_NOT_FOUND)
        -- neither of which is in STAT_MISSING_WINERRORS (21/123/1921,
        the codes errno alone doesn't already cover). Regression test for
        short-circuiting on "winerror is not None" and never falling back
        to the errno check once winerror happens to be set -- that would
        misclassify this, the single most common not-found case on
        Windows, as "not missing"."""
        exc = FileNotFoundError(errno.ENOENT, "The system cannot find the file")
        exc.winerror = 2  # type: ignore[attr-defined]
        assert is_missing_errno(exc) is True


class TestIsRegularFile:
    """Tests for is_regular_file()."""

    def test_regular_file(self, tmp_path: Path) -> None:
        path = tmp_path / "a.txt"
        path.write_text("a", encoding="utf-8")
        assert is_regular_file(path) is True

    def test_directory_is_not_regular(self, tmp_path: Path) -> None:
        assert is_regular_file(tmp_path) is False

    def test_missing_is_false(self, tmp_path: Path) -> None:
        assert is_regular_file(tmp_path / "missing") is False

    def test_under_a_regular_file_is_false(self, tmp_path: Path) -> None:
        path = tmp_path / "a.txt"
        path.write_text("a", encoding="utf-8")
        assert is_regular_file(path / "child") is False

    @pytest.mark.parametrize("mode", STAT_MODES)
    def test_stat_denied_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
    ) -> None:
        """Unlike Path.is_file() on Python 3.14, which returns False."""
        path = tmp_path / "locked" / "a.txt"
        path.parent.mkdir()
        path.write_text("a", encoding="utf-8")
        with deny(path, mode, monkeypatch), pytest.raises(PermissionError):
            is_regular_file(path)


@pytest.mark.parametrize("mode", ALL_MODES)
def test_deny_is_undone_when_its_block_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """The shared helper denies inside its block only."""
    path = tmp_path / "locked" / "a.txt"
    path.parent.mkdir()
    path.write_text("a", encoding="utf-8")
    with deny(path, mode, monkeypatch), pytest.raises(PermissionError):
        # Either failure a real denial gives.
        is_regular_file(path)
        path.read_bytes()
    assert is_regular_file(path)
    assert path.read_bytes() == b"a"
