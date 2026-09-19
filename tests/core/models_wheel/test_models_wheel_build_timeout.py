# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``--build-timeout``/``BuildOptions`` threading through
``get_wheel_files()``/``_discover_included_files()``'s ``--allow-build``
dispatch.

Split out of tests/core/models_wheel/test_models_wheel_allow_build.py to
keep both files under this repo's file-size soft limit -- no relationship
to that file's own tests beyond both covering ``get_wheel_files()``
dispatch with ``BuildOptions(allow=True)``.

See also: tests/core/models_wheel/test_models_wheel_allow_build.py for
every other ``--allow-build`` dispatch behavior (unaffected by
``build_timeout``'s addition);
tests/core/models_wheel/test_models_wheel_build_and_read.py for
``build_and_read_wheel()``'s own timeout handling
(``BuildTimeoutError``/``KeyboardInterrupt``), which this dispatch-level
file does not re-test; tests/core/test_build_options.py for timeout
validation, which happens when ``BuildOptions`` is constructed.
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


def test_allow_build_settings_reach_build_and_read_no_static_module(
    tmp_path: Path,
) -> None:
    """``BuildSettings`` (isolated, timeout) reaches ``build_and_read_wheel()``
    unchanged at the no-static-module call site (uv_build)."""
    _make_backend_project(tmp_path, "uv_build")

    with mock.patch(
        "pitloom.core._models_wheel_build_and_read.build_and_read_wheel",
        autospec=True,
        return_value=None,
    ) as mock_build:
        get_wheel_files(
            tmp_path,
            build_options=BuildOptions(allow=True, no_isolation=True, timeout=45),
        )

    mock_build.assert_called_once_with(tmp_path, isolated=False, timeout=45)


def test_allow_build_settings_reach_build_and_read_registered_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``BuildSettings`` also reaches ``build_and_read_wheel()`` unchanged
    at the registered-backend-static-discovery-failed call site
    (setuptools) -- the second of the two call sites in
    ``_models_wheel_dispatch.py``."""
    _make_backend_project(tmp_path, "setuptools.build_meta")

    def _failed_setuptools_discover(
        project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile] | None:
        del project_dir, pyproject_data
        return None

    monkeypatch.setattr(
        "pitloom.core._models_wheel_setuptools.discover", _failed_setuptools_discover
    )

    with mock.patch(
        "pitloom.core._models_wheel_build_and_read.build_and_read_wheel",
        autospec=True,
        return_value=None,
    ) as mock_build:
        get_wheel_files(tmp_path, build_options=BuildOptions(allow=True, timeout=90))

    mock_build.assert_called_once_with(tmp_path, isolated=True, timeout=90)


def test_allow_build_security_warning_shows_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The security-relevant "invoking a real PEP 517 build" ``WARNING:``
    must show the resolved timeout in seconds."""
    _make_backend_project(tmp_path, "uv_build")

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
        "pitloom.core._models_wheel_hatchling.discover", lambda project_dir: []
    )

    with caplog.at_level(logging.WARNING):
        get_wheel_files(tmp_path, build_options=BuildOptions(allow=True, timeout=333))

    assert "--allow-build is invoking a real PEP 517 build" in caplog.text
    assert "timeout 333s" in caplog.text


def test_allow_build_timeout_fallback_warning_still_fires(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """When build-and-read itself times out (returns ``None``, same as
    any other failure from this dispatch level's point of view -- the
    timeout-specific ``WARNING:`` is logged inside
    ``build_and_read_wheel()`` itself, not here), the Hatchling fallback
    ``WARNING:`` must still fire -- a timeout is not a special case at
    this dispatch level."""
    _make_backend_project(tmp_path, "uv_build")

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
        "pitloom.core._models_wheel_hatchling.discover", lambda project_dir: []
    )

    with caplog.at_level(logging.WARNING):
        get_wheel_files(tmp_path, build_options=BuildOptions(allow=True, timeout=5))

    assert "build-and-read failed" in caplog.text


def test_stray_build_flags_never_start_a_build(tmp_path: Path) -> None:
    """``no_isolation``/``timeout`` without ``allow`` must never reach
    ``build_and_read_wheel()`` -- a timeout alone is not an opt-in."""
    _make_backend_project(tmp_path, "uv_build")

    with mock.patch(
        "pitloom.core._models_wheel_build_and_read.build_and_read_wheel"
    ) as mock_build:
        get_wheel_files(
            tmp_path, build_options=BuildOptions(no_isolation=True, timeout=45)
        )

    mock_build.assert_not_called()
