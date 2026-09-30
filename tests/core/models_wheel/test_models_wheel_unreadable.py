# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``get_wheel_files()`` skips an unreadable file alone, with one warning.

A discovered file that exists but cannot be read is a genuine failure:
one ``WARNING: FILE=<project-relative path>: ...`` and that file is left
out, every other file stays. A discovered path that is missing or not a
regular file is normal absence: skipped with no warning.

See also: tests/_unreadable.py (the deny modes),
tests/test_unreadable_file_surfaces.py (every surface),
tests/core/test_path_probe.py (the stat() classification).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.core._models_wheel_types import IncludedFile
from pitloom.core.models import get_wheel_files
from pitloom.core.project import ProjectFile
from tests._unreadable import ALL_MODES, deny
from tests.warning_helpers import file_values

_SECRET = "demo/locked/secret.txt"


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "demo" / "locked").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (root / _SECRET).write_text("secret\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n\n'
        '[project]\nname = "demo"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    return root


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


def _paths(files: list[ProjectFile]) -> list[str]:
    return [f.physical_path for f in files]


def _fake_discovery(
    monkeypatch: pytest.MonkeyPatch,
    included: list[IncludedFile],
    cleanups: list[str],
) -> None:
    def _discover(
        *_args: object, **_kwargs: object
    ) -> tuple[list[IncludedFile], Callable[[], None]]:
        return included, lambda: cleanups.append("cleaned")

    monkeypatch.setattr(
        "pitloom.core._models_wheel._discover_included_files", _discover
    )


@pytest.mark.parametrize("skip_merkle_root", [False, True])
@pytest.mark.parametrize("mode", ALL_MODES)
def test_unreadable_file_is_skipped_with_one_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    mode: str,
    skip_merkle_root: bool,
) -> None:
    project = _project(tmp_path)
    baseline_root, baseline, _ = get_wheel_files(
        project, skip_merkle_root=skip_merkle_root
    )
    # The file is really part of the scan when readable.
    assert _SECRET in _paths(baseline)

    with (
        deny(project / _SECRET, mode, monkeypatch),
        caplog.at_level(logging.WARNING, logger="pitloom"),
    ):
        root, files, cleanup = get_wheel_files(
            project, skip_merkle_root=skip_merkle_root
        )
    cleanup()

    assert _paths(files) == ["demo/__init__.py"]
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert warnings[0].startswith(f"FILE={_SECRET}: could not read")
    if skip_merkle_root:
        assert root is None
    else:
        # The root covers the readable files only: same as without the file.
        (project / _SECRET).unlink()
        expected_root, _, _ = get_wheel_files(project)
        assert root == expected_root
        assert root != baseline_root


def test_missing_or_non_regular_path_is_skipped_silently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Absence is not an error: no warning, the readable file stays."""
    project = _project(tmp_path)
    real = project / "demo" / "__init__.py"
    included = [
        IncludedFile(str(real), "demo/__init__.py"),
        IncludedFile(str(project / "demo" / "gone.py"), "demo/gone.py"),
        IncludedFile(str(project / "demo" / "locked"), "demo/locked"),
        # ENOTDIR: a path "under" a regular file.
        IncludedFile(str(real / "child.py"), "demo/__init__.py/child.py"),
    ]
    _fake_discovery(monkeypatch, included, [])
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        root, files, _ = get_wheel_files(project)

    assert _paths(files) == ["demo/__init__.py"]
    assert root is not None
    assert not _warnings(caplog)


def test_unreadable_file_outside_project_is_named_by_distribution_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A build-and-read file lives in a temporary directory: the warning
    names its stable distribution path, never the temporary one."""
    project = _project(tmp_path)
    extracted = tmp_path / "extract-tmp" / "demo" / "data.bin"
    extracted.parent.mkdir(parents=True)
    extracted.write_bytes(b"\x00\x01")
    included = [
        IncludedFile(str(project / "demo" / "__init__.py"), "demo/__init__.py"),
        IncludedFile(str(extracted), "demo/data.bin"),
    ]
    _fake_discovery(monkeypatch, included, [])
    with (
        deny(extracted, "open", monkeypatch),
        caplog.at_level(logging.WARNING, logger="pitloom"),
    ):
        _, files, _ = get_wheel_files(project)

    assert _paths(files) == ["demo/__init__.py"]
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert warnings[0].startswith("FILE=demo/data.bin: could not read")
    assert file_values(warnings) == ["demo/data.bin"]


def test_every_file_unreadable_returns_no_files_and_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    project = _project(tmp_path)
    secret = project / _SECRET
    cleanups: list[str] = []
    _fake_discovery(monkeypatch, [IncludedFile(str(secret), _SECRET)], cleanups)
    with (
        deny(secret, "open", monkeypatch),
        caplog.at_level(logging.WARNING, logger="pitloom"),
    ):
        root, files, cleanup = get_wheel_files(project)

    assert (root, files) == (None, [])
    assert cleanups == ["cleaned"]
    cleanup()  # the no-op handed back; discovery's cleanup ran once only
    assert cleanups == ["cleaned"]
    assert len(_warnings(caplog)) == 1


def test_non_os_error_propagates_after_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a read/access failure is skipped: a bug is not turned into a
    silently empty file list."""
    project = _project(tmp_path)
    cleanups: list[str] = []
    _fake_discovery(
        monkeypatch,
        [IncludedFile(str(project / "demo" / "__init__.py"), "demo/__init__.py")],
        cleanups,
    )

    def _boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr("pitloom.core._models_wheel._build_project_file_entry", _boom)
    with pytest.raises(RuntimeError, match="boom"):
        get_wheel_files(project)
    assert cleanups == ["cleaned"]
