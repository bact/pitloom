# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared pytest fixtures and configuration."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture(autouse=True)
def _block_pypi_network_lookups(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Make PyPI JSON API dependency enrichment act as if offline, by default.

    ``add_dependencies`` (``pitloom.assemble.spdx3.deps``) makes a real
    network request per dependency unless ``offline=True`` is threaded all
    the way from the caller -- which most existing SBOM-generation tests
    don't do, since that plumbing didn't exist when they were written.
    Without this, the whole suite would silently start making live network
    calls, become slow, flaky, and fail offline/CI-sandboxed runs. Tests
    that specifically exercise the PyPI fallback path opt out via the
    ``pypi_network`` marker.
    """
    if "pypi_network" in request.keywords:
        return
    monkeypatch.setattr(
        "pitloom.assemble.spdx3.deps._fetch_pypi_release_info",
        lambda name, version: None,
    )
