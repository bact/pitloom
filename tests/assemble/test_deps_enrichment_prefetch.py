# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for the concurrent PyPI release-info prefetch, a live
PyPI JSON API sanity check, and supplier/originator/remote-authors
handling in ``pitloom.assemble.spdx3.deps``.

See also: test_deps_enrichment_names_versions.py,
test_deps_enrichment_supplier_license.py,
test_deps_enrichment_pypi_fallback.py -- this module's siblings, split from
the original test_deps_enrichment.py.
"""

# pylint: disable=protected-access
# pylint: disable=missing-function-docstring

from __future__ import annotations

import time
from importlib.metadata import PackageNotFoundError
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import deps_installed as deps_mod
from pitloom.assemble.spdx3 import deps_pypi, deps_supplier
from pitloom.assemble.spdx3.deps import add_dependencies
from pitloom.assemble.spdx3.deps_pypi import (
    _extract_release_hash,
    _fetch_pypi_release_info,
    _prefetch_pypi_release_infos,
)
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid, generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

from .conftest import _FakeMetadata, _make_ci


def _uninstalled(*_args: object, **_kwargs: object) -> None:
    raise PackageNotFoundError


# ---------------------------------------------------------------------------
# _prefetch_pypi_release_infos -- concurrency, dedup, offline integration
# ---------------------------------------------------------------------------


def test_prefetch_pypi_release_infos_runs_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: add_dependencies used to fetch each dependency from
    PyPI sequentially -- N dependencies cost N blocking round-trips (each
    up to _PYPI_TIMEOUT_SECONDS on failure) instead of roughly one."""

    def _slow_fetch(_name: str, _version: str | None) -> None:
        time.sleep(0.2)

    monkeypatch.setattr(deps_pypi, "_fetch_pypi_release_info", _slow_fetch)

    start = time.monotonic()
    _prefetch_pypi_release_infos([(f"pkg{i}", "unknown") for i in range(6)])
    elapsed = time.monotonic() - start

    # Sequential would be >= 1.2s (6 * 0.2s); concurrent should be close to
    # the single-fetch latency. Generous bound to absorb CI/scheduler noise.
    assert elapsed < 0.8


def test_prefetch_pypi_release_infos_dedupes_same_name_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def _counting_fetch(_name: str, _version: str | None) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return {"info": {}}

    monkeypatch.setattr(deps_pypi, "_fetch_pypi_release_info", _counting_fetch)

    _prefetch_pypi_release_infos(
        [("samepkg", "1.0.0"), ("samepkg", "1.0.0"), ("samepkg", "1.0.0")]
    )
    assert call_count == 1


def test_prefetch_pypi_release_infos_normalizes_unknown_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_versions: list[str | None] = []

    def _record_fetch(_name: str, version: str | None) -> None:
        seen_versions.append(version)

    monkeypatch.setattr(deps_pypi, "_fetch_pypi_release_info", _record_fetch)

    _prefetch_pypi_release_infos([("pkg", "unknown")])
    assert seen_versions == [None]


def test_prefetch_pypi_release_infos_empty_input() -> None:
    assert not _prefetch_pypi_release_infos([])


def test_add_dependencies_uses_prefetch_cache_not_individual_fetches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """add_dependencies must fetch each distinct dependency's PyPI data
    exactly once via the concurrent prefetch, not once per call inside
    the per-dependency enrichment loop."""
    monkeypatch.setattr(deps_mod, "get_package_version", _uninstalled)
    monkeypatch.setattr(deps_mod, "get_pkg_metadata", _uninstalled)

    call_count = 0

    def _counting_fetch(_name: str, _version: str | None) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return {"info": {"license_expression": "MIT"}}

    monkeypatch.setattr(deps_pypi, "_fetch_pypi_release_info", _counting_fetch)

    doc_uuid = compute_doc_uuid("prefetchtest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    main_pkg = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="prefetchtest", doc_uuid=doc_uuid),
        name="prefetchtest",
        creationInfo=ci,
    )
    exporter.add_package(main_pkg)

    add_dependencies(
        ["pkg-a==1.0", "pkg-b==1.0", "pkg-c==1.0"],
        "Source: pyproject.toml | Field: project.dependencies",
        require_spdx_id(main_pkg),
        ci,
        "prefetchtest",
        doc_uuid,
        exporter,
        offline=False,
    )

    assert call_count == 3


# ---------------------------------------------------------------------------
# Live PyPI JSON API sanity check -- real network, opts out of conftest's
# default block. "packaging" is a long-established, guaranteed-published
# PyPI project, chosen to keep this stable over time.
# ---------------------------------------------------------------------------


@pytest.mark.pypi_network
def test_fetch_pypi_release_info_live_network() -> None:
    release_info = _fetch_pypi_release_info("packaging", None)
    assert release_info is not None
    assert release_info["info"]["name"].lower() == "packaging"
    digest = _extract_release_hash(release_info)
    assert digest is not None
    assert len(digest) == 64  # hex sha256


def test_extract_suppliers_parses_comma_separated_names() -> None:
    meta = _FakeMetadata({"Author": "Alice, Bob and Charlie"})
    assert deps_supplier._resolve_supplier(meta) == [
        ("Alice", None),
        ("Bob", None),
        ("Charlie", None),
    ]


def test_apply_originator_creates_others_external_ref() -> None:
    doc_uuid = compute_doc_uuid("otherstest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    dep_package = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="otherstest", doc_uuid=doc_uuid),
        name="test",
        creationInfo=ci,
    )
    exporter.add_package(dep_package)

    originators: list[tuple[str | None, str | None]] = [
        ("Alice", None),
        ("Others (See OTHER_AUTHORS.md)", None),
    ]
    deps_supplier._apply_originator(
        originators,
        dep_package,
        ci,
        "otherstest",
        doc_uuid,
        exporter,
        repo_url="https://github.com/foo/bar.git",
        offline=True,
    )

    agents = [
        o
        for o in exporter.object_set.objects
        if isinstance(o, (spdx3.Person, spdx3.Organization))
    ]
    assert len(agents) == 2

    others = next(
        (
            a
            for a in agents
            if a.name and "Others" in a.name and isinstance(a, spdx3.Organization)
        ),
        None,
    )
    assert others is not None
    assert len(others.externalRef) == 1
    ref = others.externalRef[0]
    assert isinstance(ref, spdx3.ExternalRef)
    assert ref.externalRefType == spdx3.ExternalRefType.documentation

    assert len(dep_package.software_attributionText) > 0
    assert (
        "Attribution: This package includes contributions from additional authors"
        in dep_package.software_attributionText[0]
    )
    assert ref.locator == ["https://github.com/foo/bar/blob/HEAD/OTHER_AUTHORS.md"]
    assert ref.comment == "Refers to OTHER_AUTHORS.md"


def test_resolve_remote_authors_file_offline_and_errors() -> None:
    """Test offline behavior and network-failure fallback for remote authors
    files.

    ``ftp://`` as the *repo_url* scheme does not exercise the function's
    "disallowed scheme" ``ValueError`` branch: ``_resolve_remote_authors_file``
    only inspects ``netloc`` (which ``urlparse`` populates the same way
    regardless of scheme) and always builds an ``https://`` raw-content URL
    for recognized hosts, so a non-http(s) *repo_url* still reaches the real
    fetch path. This test therefore mocks the fetch instead of relying on a
    real (and previously unmocked) network call.
    """
    # Test offline returns immediately without trying to fetch
    locator, ctype, content = deps_supplier._resolve_remote_authors_file(
        "https://github.com/foo/pkg",
        "AUTHORS",
        offline=True,
        content_type_method="auto",
    )
    assert locator == "https://github.com/foo/pkg/blob/HEAD/AUTHORS"
    assert ctype is None
    assert content is None

    # Test the URLError/OSError fallback path returns a locator-only result,
    # without making a real network call.
    with patch("urllib.request.urlopen", side_effect=URLError("simulated failure")):
        locator, ctype, content = deps_supplier._resolve_remote_authors_file(
            "https://github.com/foo/pkg-offline-fallback",
            "AUTHORS",
            offline=False,
            content_type_method="auto",
        )
    assert locator == "https://github.com/foo/pkg-offline-fallback/blob/HEAD/AUTHORS"
    assert ctype is None
    assert content is None

    # Test lru_cache behavior (call twice, check it returns identical)
    # without hitting the network again on the second call.
    locator2, ctype2, content2 = deps_supplier._resolve_remote_authors_file(
        "https://github.com/foo/pkg-offline-fallback",
        "AUTHORS",
        offline=False,
        content_type_method="auto",
    )
    assert locator2 == locator
    assert ctype2 == ctype
    assert content2 == content


@patch("urllib.request.urlopen")
def test_resolve_remote_authors_file_success_and_branches(
    mock_urlopen: MagicMock,
) -> None:
    """Test successful URL fetch and other repository branches."""
    # Mock successful response
    mock_response = MagicMock()
    mock_response.read.return_value = b"Author1\nAuthor2"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    # Test github.com with successful fetch
    locator, _ctype, content = deps_supplier._resolve_remote_authors_file(
        "https://github.com/foo/pkg",
        "AUTHORS",
        offline=False,
        content_type_method="auto",
    )
    assert locator == "https://github.com/foo/pkg/blob/HEAD/AUTHORS"
    assert content == "Author1\nAuthor2"

    # Test gitlab.com
    locator, _ctype, content = deps_supplier._resolve_remote_authors_file(
        "https://gitlab.com/foo/pkg",
        "AUTHORS",
        offline=True,
        content_type_method="auto",
    )
    assert locator == "https://gitlab.com/foo/pkg/-/blob/HEAD/AUTHORS"

    # Test unknown host
    locator, _ctype, content = deps_supplier._resolve_remote_authors_file(
        "https://example.com/foo/pkg",
        "AUTHORS",
        offline=True,
        content_type_method="auto",
    )
    assert locator == "https://example.com/foo/pkg"

    # Test short path
    locator, _ctype, content = deps_supplier._resolve_remote_authors_file(
        "https://github.com/foo",
        "AUTHORS",
        offline=True,
        content_type_method="auto",
    )
    assert locator == "https://github.com/foo"
