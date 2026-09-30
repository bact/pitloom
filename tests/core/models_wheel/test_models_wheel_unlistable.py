# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A directory discovery cannot list: one warning, the rest still listed.

Every backend walks through its own library, none with an ``onerror``;
``warn_unlistable_dirs()`` sees the attempted listings through an audit
hook and warns once per directory that fails for a reason other than
absence.

See also: tests/_unreadable.py (``unlistable()``),
tests/test_unreadable_file_surfaces.py (every surface),
tests/core/models_wheel/test_models_wheel_unreadable.py (one file).
"""

from __future__ import annotations

import errno
import logging
import os
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pitloom.core._models_wheel_unlistable import warn_unlistable_dirs
from pitloom.core.models import get_wheel_files
from tests._unreadable import POSIX_NON_ROOT, unlistable

_BACKENDS = {
    "hatchling": "hatchling.build",
    "setuptools": "setuptools.build_meta",
    "flit": "flit_core.buildapi",
    "pdm": "pdm.backend",
    "poetry": "poetry.core.masonry.api",
    # No static module: the Hatchling-heuristic fallback.
    "uv_build": "uv_build",
}
_HIDDEN = "pkg/sub/a.py"
_KEPT = "pkg/ok/b.py"
_PREFIX = "DIR="


def _project(tmp_path: Path, build_backend: str) -> Path:
    root = tmp_path / "proj"
    for name in ("pkg/__init__.py", "pkg/sub/__init__.py", _HIDDEN):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text('"""Doc."""\n', encoding="utf-8")
    (root / "pkg/ok").mkdir()
    (root / "pkg/ok/__init__.py").write_text("", encoding="utf-8")
    (root / _KEPT).write_text("", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        f'[build-system]\nrequires = ["x"]\nbuild-backend = "{build_backend}"\n\n'
        '[project]\nname = "pkg"\nversion = "1.0.0"\ndescription = "Doc."\n',
        encoding="utf-8",
    )
    return root


def _dir_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(_PREFIX)
    ]


def _discovered(root: Path) -> set[str]:
    _, files, cleanup = get_wheel_files(root, skip_merkle_root=True)
    cleanup()
    return {f.physical_path for f in files}


@pytest.mark.skipif(not POSIX_NON_ROOT, reason="needs POSIX permissions, non-root")
@pytest.mark.parametrize("backend", sorted(_BACKENDS))
def test_unlistable_dir_warns_once_and_keeps_the_rest(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, backend: str
) -> None:
    root = _project(tmp_path, _BACKENDS[backend])
    # Not vacuous: listable, the backend discovers the hidden file.
    assert {_HIDDEN, _KEPT} <= _discovered(root)

    with unlistable(root / "pkg/sub"), caplog.at_level(logging.WARNING):
        discovered = _discovered(root)

    assert _KEPT in discovered
    assert _HIDDEN not in discovered
    (message,) = _dir_warnings(caplog)
    assert message.startswith("DIR=pkg/sub: could not list for file discovery; ")


@pytest.fixture(name="deny_scandir")
def _deny_scandir(monkeypatch: pytest.MonkeyPatch) -> Iterator[set[str]]:
    """``os.scandir()`` of any path added to the yielded set raises
    ``PermissionError``; ``os.listdir()`` stays real, so a listing inside
    the block is recorded."""
    denied: set[str] = set()
    real_scandir = os.scandir

    def _scandir(path: Any = ".") -> Any:
        if os.path.abspath(path) in denied:
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), path)
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", _scandir)
    yield denied


@pytest.mark.parametrize(("relative", "expected"), [("a/b", "a/b"), ("", ".")])
def test_denied_listing_is_named_project_relative(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    deny_scandir: set[str],
    relative: str,
    expected: str,
) -> None:
    target = tmp_path / relative
    target.mkdir(parents=True, exist_ok=True)
    deny_scandir.add(os.path.abspath(target))
    with caplog.at_level(logging.WARNING), warn_unlistable_dirs(tmp_path):
        os.listdir(target)
    (message,) = _dir_warnings(caplog)
    assert message.startswith(f"DIR={expected}: could not list for file discovery")


def test_relative_listing_resolves_against_cwd_at_call_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    deny_scandir: set[str],
) -> None:
    """setuptools and pdm-backend chdir() into the project and list
    relative names; the cwd is restored before the probe runs."""
    (tmp_path / "sub").mkdir()
    deny_scandir.add(os.path.abspath(tmp_path / "sub"))
    with caplog.at_level(logging.WARNING), warn_unlistable_dirs(tmp_path):
        with monkeypatch.context() as patch:
            patch.chdir(tmp_path)
            os.listdir("sub")
    assert [m.split(":", 1)[0] for m in _dir_warnings(caplog)] == ["DIR=sub"]


def test_quiet_cases(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, deny_scandir: set[str]
) -> None:
    """Missing, outside the project, another thread, outside the block."""
    project = tmp_path / "proj"
    outside = tmp_path / "outside"
    other = project / "other"
    for directory in (outside, other):
        directory.mkdir(parents=True)
        deny_scandir.add(os.path.abspath(directory))
    os.listdir(other)  # before the block: not recorded
    with caplog.at_level(logging.WARNING), warn_unlistable_dirs(project):
        with pytest.raises(FileNotFoundError):
            os.listdir(project / "missing")
        os.listdir(outside)
        thread = threading.Thread(target=os.listdir, args=(other,))
        thread.start()
        thread.join()
    assert not _dir_warnings(caplog)


def test_block_that_raises_logs_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, deny_scandir: set[str]
) -> None:
    deny_scandir.add(os.path.abspath(tmp_path))
    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(RuntimeError, match="boom"),
        warn_unlistable_dirs(tmp_path),
    ):
        os.listdir(tmp_path)
        raise RuntimeError("boom")
    assert not _dir_warnings(caplog)


@pytest.mark.parametrize("args", [(), (3,), (object(),), (b"bytes-name",)])
def test_hook_never_fails_the_audited_call(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, args: tuple[object, ...]
) -> None:
    """An exception in an audit hook would fail the listing call itself."""
    with caplog.at_level(logging.WARNING), warn_unlistable_dirs(tmp_path):
        sys.audit("os.scandir", *args)
    assert not _dir_warnings(caplog)


def test_multi_line_error_is_one_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _scandir(_path: Any = ".") -> Any:
        raise PermissionError(errno.EACCES, "denied\nsecond line")

    with caplog.at_level(logging.WARNING), warn_unlistable_dirs(tmp_path):
        os.listdir(tmp_path)
        monkeypatch.setattr(os, "scandir", _scandir)
    (message,) = _dir_warnings(caplog)
    assert "\n" not in message
    assert message.endswith("denied second line")
