# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared pytest fixtures and configuration."""

import socket
from pathlib import Path
from typing import Any

import pytest

from pitloom.extract._license import _get_matcher

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class _NetworkBlockedError(RuntimeError):
    """Raised when a test tries to open a real network socket."""


def _blocked_socket(*_args: Any, **_kwargs: Any) -> None:
    raise _NetworkBlockedError(
        "Real network access attempted during a test. Mock the network call "
        "(e.g. patch urllib.request.urlopen / fetch_json), or opt in "
        "explicitly with @pytest.mark.pypi_network if the test genuinely "
        "needs a live socket."
    )


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture(autouse=True)
def _reset_license_matcher_cache() -> None:
    """Clear the cached ``AggregatedLicenseMatcher`` before each test, so a
    mock from one test can't leak into the next via ``_get_matcher``'s cache."""
    _get_matcher.cache_clear()


@pytest.fixture(autouse=True)
def _block_network_access(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Block real outbound sockets during tests, by default.

    Several code paths (PyPI JSON API dependency enrichment, remote
    ``AUTHORS`` file fetches) make real network requests unless the caller
    threads ``offline=True`` all the way through -- which not every test
    does, since some of that plumbing didn't exist when the tests were
    written. Without this guard, a forgotten mock silently turns into a
    live network call: slow, flaky, and broken in offline/CI-sandboxed
    runs. Tests that genuinely need a live socket opt out via the
    ``pypi_network`` marker.
    """
    if "pypi_network" in request.keywords:
        return
    monkeypatch.setattr(
        "pitloom.assemble.spdx3.deps_pypi._fetch_pypi_release_info",
        lambda name, version: None,
    )
    monkeypatch.setattr(socket, "socket", _blocked_socket)
