# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared pytest fixtures and configuration."""

import json
import logging
import socket
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pitloom.extract._license import _get_matcher
from pitloom.logging_config import _WARNED_ONCE

# pylint: disable-next=unused-import
from tests._network import (  # noqa: F401
    pytest_configure,
    pytest_make_collect_report,
    pytest_runtest_makereport,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

#: Longest test node id allowed. pytest puts the id in the
#: PYTEST_CURRENT_TEST environment variable, which Windows caps at 32,767
#: characters: a long parametrize value needs a short explicit ``ids=``.
MAX_NODEID_LENGTH = 1000


@pytest.fixture(autouse=True)
def _short_nodeid(request: pytest.FixtureRequest) -> None:
    """Fail any test whose node id is over :data:`MAX_NODEID_LENGTH`, on
    every platform, not only where the environment variable overflows. A
    fixture, not a collection hook: xdist drops the message of an
    exception raised in ``pytest_collection_modifyitems``."""
    if len(request.node.nodeid) > MAX_NODEID_LENGTH:
        pytest.fail(
            f"node id over {MAX_NODEID_LENGTH} characters;"
            " give the parametrize a short ids=",
            pytrace=False,
        )


def _assert_no_duplicate_spdx_ids(
    sbom_json: str | None = None, exporter: Any | None = None
) -> None:
    """Assert no two elements share a ``spdxId``.

    Pass *exporter* (a :class:`~pitloom.export.spdx3_json.Spdx3JsonExporter`)
    whenever the caller has one: checking its ``object_set`` directly is
    the strict form, since Pitloom's own ``_deduplicate_named_elements``
    (``pitloom.export.spdx3_json``) silently drops a later same-id element
    from the *serialized* ``@graph`` whenever its fields are byte-for-byte
    identical to an earlier one -- which can mask a genuine duplicate id
    on two elements that happen to carry identical content (e.g. two
    same-fallback-name AI model packages). Pass *sbom_json* (the
    generator's own returned string) instead when no exporter is
    reachable, e.g. a test that only calls a public
    ``generate_*_sbom()``/CLI entry point.
    """
    if exporter is not None:
        ids = [
            str(obj.spdxId)
            for obj in exporter.object_set.objects
            if getattr(obj, "spdxId", None)
        ]
    else:
        assert sbom_json is not None, "pass sbom_json or exporter"
        graph = json.loads(sbom_json)["@graph"]
        ids = [e["spdxId"] for e in graph if "spdxId" in e]
    assert len(ids) == len(set(ids)), f"duplicate spdxId: {sorted(ids)}"


def fake_build_and_read_path(*parts: str) -> str:
    """A path string that mimics ``--allow-build``'s fresh
    ``tempfile.mkdtemp()`` extraction directory (see
    ``ProjectFile.physical_path``'s docstring): genuinely absolute
    under the current platform's own :mod:`pathlib` semantics, never
    project-relative.

    A hardcoded POSIX literal such as ``"/tmp/xyz"`` is *not* absolute
    under ``WindowsPath`` semantics (``is_absolute()`` requires a drive
    letter there) -- using one silently stops exercising the
    absolute-``physical_path`` branch under test on Windows CI, even
    though the equivalent real value (from a real ``tempfile.mkdtemp()``
    on Windows) always carries a drive letter and is genuinely absolute.
    """
    return Path(tempfile.gettempdir(), "pitloom-build-and-read-fake", *parts).as_posix()


class _NetworkBlockedError(RuntimeError):
    """Raised when a test tries to open a real network socket."""


def _blocked_socket(*_args: Any, **_kwargs: Any) -> None:
    raise _NetworkBlockedError(
        "Real network access attempted during a test. Mock the network call "
        "(e.g. patch urllib.request.urlopen / fetch_json), or opt in "
        "explicitly with @pytest.mark.network if the test genuinely "
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
def _reset_warn_once_state() -> None:
    """Clear ``warn_once()``'s per-process dedup state before each test, so
    one test's WARNING->DEBUG downgrade can't leak into the next and hide a
    real warn_once regression."""
    _WARNED_ONCE.clear()


@pytest.fixture(autouse=True)
def _restore_pitloom_logger() -> Iterator[None]:
    """Put the ``pitloom`` logger's handlers and level back after each test.

    ``configure_logging()`` binds a handler to the ``sys.stderr`` of the
    moment, which under ``capsys``/``capfd`` is a capture stream closed when
    that test ends. Left in place, a later test on the same worker that logs
    gets ``--- Logging error ---`` on its stderr (a closed file), so any test
    asserting an empty stderr fails depending on xdist ordering.
    """
    logger = logging.getLogger("pitloom")
    handlers, level = logger.handlers, logger.level
    yield
    logger.handlers = handlers
    logger.setLevel(level)


@pytest.fixture(autouse=True)
def _restore_int_digit_limit() -> Iterator[None]:
    """Put CPython's ``int_max_str_digits`` back after each test: a test may
    change it with ``sys.set_int_max_str_digits``, and it is process-global.
    CPython 3.10.0-3.10.6 has no such limit."""
    getter = getattr(sys, "get_int_max_str_digits", None)
    setter = getattr(sys, "set_int_max_str_digits", None)
    saved = getter() if getter is not None else None
    yield
    if setter is not None:
        setter(saved)


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
    ``network`` marker.
    """
    if "network" in request.keywords:
        return
    monkeypatch.setattr(
        "pitloom.assemble.spdx3.deps_pypi._fetch_pypi_release_info",
        lambda name, version: None,
    )
    monkeypatch.setattr(socket, "socket", _blocked_socket)
