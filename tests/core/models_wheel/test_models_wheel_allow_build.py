# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``--allow-build``'s build-and-read fallback at the
``get_wheel_files()``/``_discover_included_files()`` dispatch level.

Split out of tests/core/models_wheel/test_models_wheel_dispatch.py
(already near this repo's file-size soft limit) purely to keep both
files under it -- no relationship to that file's own tests beyond both
covering ``get_wheel_files()`` dispatch.

See also: tests/core/models_wheel/test_models_wheel_build_and_read.py
for the generic mechanism's own standalone unit tests;
tests/core/models_wheel/test_models_wheel_dispatch.py for
``test_get_wheel_files_unhandled_backend_falls_back_with_warning``, which
this file's tests complement (uv_build's ``allow_build=False`` case is
covered there and deliberately left unchanged by this feature);
tests/core/models_wheel/test_models_wheel_build_timeout.py for
``--build-timeout``/``BuildSettings`` threading at this same dispatch
level, split out to keep both files under this repo's file-size soft
limit.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import pytest

from pitloom.core._models_wheel_types import IncludedFile
from pitloom.core.build_options import BuildOptions
from pitloom.core.models import get_wheel_files

BuildAndReadResult = tuple[list[IncludedFile], Callable[[], None]] | None


def _make_backend_project(tmp_path: Path, build_backend: str) -> None:
    (tmp_path / "pyproject.toml").write_text(
        f'[build-system]\nrequires = ["{build_backend.split(".", maxsplit=1)[0]}"]\n'
        f'build-backend = "{build_backend}"\n\n'
        '[project]\nname = "pkg"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )


def _recording_hatchling_discover(
    calls: list[Path],
) -> Callable[[Path], list[IncludedFile]]:
    """A fake Hatchling ``discover()`` that records every call it
    receives, for asserting it either was or wasn't reached."""

    def _discover(project_dir: Path) -> list[IncludedFile]:
        calls.append(project_dir)
        return []

    return _discover


def test_allow_build_dispatches_unhandled_backend_to_build_and_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A backend with no static discovery module (uv_build) reaches
    ``build_and_read_wheel()`` when ``allow_build=True``, never
    Hatchling."""
    _make_backend_project(tmp_path, "uv_build")
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")

    def _fake_build_and_read(
        project_dir: Path, *, isolated: bool = True, timeout: int = 1200
    ) -> BuildAndReadResult:
        del project_dir, isolated, timeout
        return (
            [IncludedFile(path=str(tmp_path / "a.py"), distribution_path="pkg/a.py")],
            lambda: None,
        )

    hatchling_called: list[Path] = []
    monkeypatch.setattr(
        "pitloom.core._models_wheel_build_and_read.build_and_read_wheel",
        _fake_build_and_read,
    )
    monkeypatch.setattr(
        "pitloom.core._models_wheel_hatchling.discover",
        _recording_hatchling_discover(hatchling_called),
    )

    _root, files, _ = get_wheel_files(tmp_path, build_options=BuildOptions(allow=True))

    assert not hatchling_called
    assert [f.distribution_path for f in files] == ["pkg/a.py"]


def test_allow_build_failure_falls_back_to_hatchling_with_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """When build-and-read itself fails (returns ``None``), the
    unhandled-backend path still falls back to the Hatchling heuristic --
    ``--allow-build``'s worst case must never be worse than not passing
    it at all."""
    _make_backend_project(tmp_path, "uv_build")
    hatchling_called: list[Path] = []

    def _fake_build_and_read(
        project_dir: Path, *, isolated: bool = True, timeout: int = 1200
    ) -> BuildAndReadResult:
        del project_dir, isolated, timeout
        return None

    monkeypatch.setattr(
        "pitloom.core._models_wheel_build_and_read.build_and_read_wheel",
        _fake_build_and_read,
    )
    monkeypatch.setattr(
        "pitloom.core._models_wheel_hatchling.discover",
        _recording_hatchling_discover(hatchling_called),
    )

    with caplog.at_level(logging.WARNING):
        get_wheel_files(tmp_path, build_options=BuildOptions(allow=True))

    assert hatchling_called
    assert "--allow-build is invoking a real PEP 517 build" in caplog.text
    assert "build-and-read failed" in caplog.text


def test_allow_build_failure_hint_does_not_suggest_allow_build_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: when build-and-read was already tried (allow_build=
    True) and failed, the fallback WARNING:'s sharpened
    [tool.uv.build-backend]-overrides hint must NOT tell the user to
    "pass --allow-build" -- they already did, and it just failed. Before
    the fix, ``_unhandled_backend_hint()`` ignored ``allow_build``
    entirely and always appended that suggestion whenever the project
    declared a file-filtering ``[tool.uv.build-backend]`` key, producing
    a self-contradictory message. Compare against the sibling
    ``allow_build=False`` case in test_models_wheel_dispatch.py's
    ``test_get_wheel_files_uv_build_fallback_warns_about_wheel_exclude``,
    where the same hint text IS expected (no build was attempted there)."""
    _make_backend_project(tmp_path, "uv_build")
    with (tmp_path / "pyproject.toml").open("a", encoding="utf-8") as f:
        f.write('\n[tool.uv.build-backend]\nwheel-exclude = ["pkg/vendored/**"]\n')

    def _fake_build_and_read(
        project_dir: Path, *, isolated: bool = True, timeout: int = 1200
    ) -> BuildAndReadResult:
        del project_dir, isolated, timeout
        return None

    monkeypatch.setattr(
        "pitloom.core._models_wheel_build_and_read.build_and_read_wheel",
        _fake_build_and_read,
    )

    with caplog.at_level(logging.WARNING):
        get_wheel_files(tmp_path, build_options=BuildOptions(allow=True))

    assert "build-and-read failed" in caplog.text
    assert "pass --allow-build" not in caplog.text


def test_allow_build_second_tier_fallback_for_registered_backend_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A REGISTERED backend (setuptools) whose own static discoverer
    fails (returns None) must reach build-and-read before Hatchling, when
    allow_build=True -- the "robustness fallback for Track A" the
    mechanism is designed to provide for every backend automatically,
    with zero backend-specific wiring."""
    _make_backend_project(tmp_path, "setuptools.build_meta")
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    hatchling_called: list[Path] = []

    def _failed_setuptools_discover(
        project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile] | None:
        del project_dir, pyproject_data
        return None

    def _fake_build_and_read(
        project_dir: Path, *, isolated: bool = True, timeout: int = 1200
    ) -> BuildAndReadResult:
        del project_dir, isolated, timeout
        return (
            [IncludedFile(path=str(tmp_path / "a.py"), distribution_path="pkg/a.py")],
            lambda: None,
        )

    monkeypatch.setattr(
        "pitloom.core._models_wheel_setuptools.discover", _failed_setuptools_discover
    )
    monkeypatch.setattr(
        "pitloom.core._models_wheel_build_and_read.build_and_read_wheel",
        _fake_build_and_read,
    )
    monkeypatch.setattr(
        "pitloom.core._models_wheel_hatchling.discover",
        _recording_hatchling_discover(hatchling_called),
    )

    _root, files, _ = get_wheel_files(tmp_path, build_options=BuildOptions(allow=True))

    assert not hatchling_called
    assert [f.distribution_path for f in files] == ["pkg/a.py"]


def test_allow_build_registered_backend_and_build_and_read_both_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """When a registered backend's static discovery fails AND the
    build-and-read fallback also fails, the function must still fall
    through to _skip_hatchling_fallback()'s give-up path (an empty
    result, not a crash) -- covers the second, distinct occurrence of
    this fallback chain (registered-backend-failure path, not the
    no-static-module path)."""
    _make_backend_project(tmp_path, "setuptools.build_meta")

    def _failed_setuptools_discover(
        project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile] | None:
        del project_dir, pyproject_data
        return None

    def _fake_build_and_read(
        project_dir: Path, *, isolated: bool = True, timeout: int = 1200
    ) -> BuildAndReadResult:
        del project_dir, isolated, timeout
        return None

    monkeypatch.setattr(
        "pitloom.core._models_wheel_setuptools.discover", _failed_setuptools_discover
    )
    monkeypatch.setattr(
        "pitloom.core._models_wheel_build_and_read.build_and_read_wheel",
        _fake_build_and_read,
    )

    with caplog.at_level(logging.WARNING):
        root, files, _ = get_wheel_files(
            tmp_path, build_options=BuildOptions(allow=True)
        )

    assert root is None
    assert files == []


def test_allow_build_never_invoked_when_registered_backend_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The inverse and equally important property: when a registered
    backend's own static discoverer already succeeds, build-and-read
    must NEVER be consulted, even with allow_build=True -- a real build
    must never run when the fast, safe static rescan already worked."""
    _make_backend_project(tmp_path, "setuptools.build_meta")
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")

    def _succeeding_setuptools_discover(
        project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile] | None:
        del project_dir, pyproject_data
        return [IncludedFile(path=str(tmp_path / "a.py"), distribution_path="pkg/a.py")]

    monkeypatch.setattr(
        "pitloom.core._models_wheel_setuptools.discover",
        _succeeding_setuptools_discover,
    )

    with mock.patch(
        "pitloom.core._models_wheel_build_and_read.build_and_read_wheel"
    ) as mock_build:
        _root, files, _ = get_wheel_files(
            tmp_path, build_options=BuildOptions(allow=True)
        )

    mock_build.assert_not_called()
    assert [f.distribution_path for f in files] == ["pkg/a.py"]


@pytest.mark.parametrize("backend_project", ["none", "hatchling"])
def test_allow_build_never_reachable_for_none_or_hatchling_backend(
    backend_project: str, tmp_path: Path
) -> None:
    """build_and_read_wheel() must never be reachable when the detected
    backend is None (no pyproject.toml at all) or explicitly Hatchling --
    both fall straight through to Hatchling's own in-process discover(),
    a separate code path not gated by allow_build at all today."""
    if backend_project == "hatchling":
        _make_backend_project(tmp_path, "hatchling.build")
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")

    with mock.patch(
        "pitloom.core._models_wheel_build_and_read.build_and_read_wheel"
    ) as mock_build:
        get_wheel_files(tmp_path, build_options=BuildOptions(allow=True))

    mock_build.assert_not_called()


def test_allow_build_cleanup_called_even_on_per_file_read_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: the cleanup callback from a build-and-read result
    must still run even when a per-file read inside get_wheel_files()'s
    shared loop raises -- otherwise a temp directory leaks silently on
    every partial failure."""
    _make_backend_project(tmp_path, "uv_build")
    cleanup_calls: list[bool] = []

    def _cleanup() -> None:
        cleanup_calls.append(True)

    def _fake_build_and_read(
        project_dir: Path, *, isolated: bool = True, timeout: int = 1200
    ) -> BuildAndReadResult:
        del project_dir, isolated, timeout
        # A real, on-disk file whose read is made to fail below --
        # source.is_file() must be True or the loop just skips it
        # silently instead of exercising the read-failure path.
        real_file = tmp_path / "a.py"
        real_file.write_text("a = 1\n", encoding="utf-8")
        return (
            [IncludedFile(path=str(real_file), distribution_path="pkg/a.py")],
            _cleanup,
        )

    def _raise_on_read(self: Path) -> bytes:
        raise OSError("boom")

    monkeypatch.setattr(
        "pitloom.core._models_wheel_build_and_read.build_and_read_wheel",
        _fake_build_and_read,
    )
    monkeypatch.setattr(Path, "read_bytes", _raise_on_read)

    root, files, _ = get_wheel_files(tmp_path, build_options=BuildOptions(allow=True))

    assert root is None
    assert files == []
    assert cleanup_calls == [True]


def test_no_build_isolation_forwarded_to_build_and_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``BuildOptions(no_isolation=True)`` must reach build_and_read_wheel() as
    ``isolated=False`` -- never silently dropped or coerced back to
    isolated."""
    _make_backend_project(tmp_path, "uv_build")
    isolated_seen: list[bool] = []

    def _fake_build_and_read(
        project_dir: Path, *, isolated: bool = True, timeout: int = 1200
    ) -> BuildAndReadResult:
        del project_dir, timeout
        isolated_seen.append(isolated)
        return None

    monkeypatch.setattr(
        "pitloom.core._models_wheel_build_and_read.build_and_read_wheel",
        _fake_build_and_read,
    )
    monkeypatch.setattr(
        "pitloom.core._models_wheel_hatchling.discover", lambda project_dir: []
    )

    get_wheel_files(tmp_path, build_options=BuildOptions(allow=True, no_isolation=True))

    assert isolated_seen == [False]
