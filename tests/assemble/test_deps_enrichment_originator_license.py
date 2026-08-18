# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for dependency originator/license resolution and the PyPI
JSON API extraction helpers used by ``pitloom.assemble.spdx3.deps``.

See also: test_deps_enrichment_names_versions.py,
test_deps_enrichment_pypi_fallback.py, test_deps_enrichment_prefetch.py --
this module's siblings, split from the original test_deps_enrichment.py.

Covers a multi-address ``Maintainer-email`` field that a naive parser
dropped entirely, and the ``License-File`` matching bug where a same-named
file outside ``.dist-info`` could be misattributed.
"""

# pylint: disable=protected-access
# pylint: disable=missing-function-docstring

from __future__ import annotations

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import deps_installed as deps_mod
from pitloom.assemble.spdx3 import deps_originator
from pitloom.assemble.spdx3.deps import _enrich_from_installed
from pitloom.assemble.spdx3.deps_originator import (
    _find_license_copyright,
    _resolve_author_or_maintainer,
)
from pitloom.assemble.spdx3.deps_pypi import (
    _extract_pypi_license,
    _extract_pypi_originator,
    _extract_release_hash,
)
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid, generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

from .conftest import _FakeMetadata, _make_ci

# ---------------------------------------------------------------------------
# _resolve_author_or_maintainer -- single address, Maintainer fallback, multi-address
# ---------------------------------------------------------------------------


def test_resolve_author_or_maintainer_from_author_email() -> None:
    meta = _FakeMetadata({"Author-email": "Trail of Bits <opensource@trailofbits.com>"})
    assert _resolve_author_or_maintainer(meta) == [
        ("Trail of Bits", "opensource@trailofbits.com")
    ]


def test_resolve_author_or_maintainer_falls_back_to_maintainer() -> None:
    meta = _FakeMetadata(
        {"Maintainer-email": "Taneli Hukkinen <hukkin@users.noreply.github.com>"}
    )
    assert _resolve_author_or_maintainer(meta) == [
        (
            "Taneli Hukkinen",
            "hukkin@users.noreply.github.com",
        )
    ]


def test_resolve_author_or_maintainer_handles_multiple_maintainer_addresses() -> None:
    """Regression: a comma-separated multi-maintainer ``Maintainer-email``
    (common in real PyPI metadata, e.g. pipdeptree's three maintainers)
    made ``email.utils.parseaddr`` -- which expects a single address --
    return ``('', '')`` for the whole field, silently dropping a real,
    usable supplier. ``email.utils.getaddresses`` parses the list
    correctly; only the first entry is used.
    """
    meta = _FakeMetadata(
        {
            "Maintainer-email": (
                "Bernát Gábor <gaborjbernat@gmail.com>, "
                "Kemal Zebari <kemalzebra@gmail.com>, "
                "Vineet Naik <naikvin@gmail.com>"
            )
        }
    )
    assert _resolve_author_or_maintainer(meta) == [
        ("Bernát Gábor", "gaborjbernat@gmail.com"),
        ("Kemal Zebari", "kemalzebra@gmail.com"),
        ("Vineet Naik", "naikvin@gmail.com"),
    ]


def test_resolve_author_or_maintainer_plain_name_no_email() -> None:
    meta = _FakeMetadata({"Author": "Some Org"})
    assert _resolve_author_or_maintainer(meta) == [("Some Org", None)]


def test_resolve_author_or_maintainer_absent_returns_none() -> None:
    assert _resolve_author_or_maintainer(_FakeMetadata({})) == []


def test_enrich_from_installed_sets_originated_by(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deps_mod,
        "get_pkg_metadata",
        lambda name: _FakeMetadata(
            {"Author-email": "Taneli Hukkinen <hukkin@users.noreply.github.com>"}
        ),
    )

    doc_uuid = compute_doc_uuid("supptest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    dep_package = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="supptest", doc_uuid=doc_uuid),
        name="tomli",
        creationInfo=ci,
    )
    dep_package.software_packageVersion = "2.4.1"
    exporter.add_package(dep_package)

    _enrich_from_installed("tomli", dep_package, ci, "supptest", doc_uuid, exporter)

    assert len(dep_package.originatedBy) > 0
    agents = [o for o in exporter.object_set.objects if isinstance(o, spdx3.Person)]
    assert len(agents) == 1
    assert agents[0].name == "Taneli Hukkinen"
    assert dep_package.originatedBy == [require_spdx_id(agents[0])]


def test_enrich_from_installed_dedupes_shared_supplier_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two dependencies with the same author must share one Agent element,
    not mint a duplicate for each."""
    monkeypatch.setattr(
        deps_mod,
        "get_pkg_metadata",
        lambda name: _FakeMetadata({"Author-email": "Same Author <same@example.com>"}),
    )

    doc_uuid = compute_doc_uuid("deduptest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()

    for dep_name in ("pkg-a", "pkg-b"):
        dep_package = spdx3.software_Package(
            spdxId=generate_spdx_id("Package", doc_name="deduptest", doc_uuid=doc_uuid),
            name=dep_name,
            creationInfo=ci,
        )
        dep_package.software_packageVersion = "1.0.0"
        exporter.add_package(dep_package)
        _enrich_from_installed(
            dep_name, dep_package, ci, "deduptest", doc_uuid, exporter
        )

    agents = [o for o in exporter.object_set.objects if isinstance(o, spdx3.Person)]
    assert len(agents) == 1


# ---------------------------------------------------------------------------
# _find_license_copyright -- License-File must be matched under .dist-info
# ---------------------------------------------------------------------------


class _FakePackagePath:
    """Minimal stand-in for ``importlib.metadata.PackagePath``."""

    def __init__(self, path: str, content: str):
        self._path = path
        self._content = content

    @property
    def name(self) -> str:
        return self._path.rsplit("/", maxsplit=1)[-1]

    def __str__(self) -> str:
        return self._path

    def read_text(self, encoding: str = "utf-8") -> str:
        _ = encoding
        return self._content


# pylint: disable-next=too-few-public-methods
class _FakeDistribution:
    def __init__(self, files: list[_FakePackagePath]):
        self.files = files


def test_find_license_copyright_ignores_same_named_file_outside_dist_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: License-File was matched by basename only
    (candidate.name != license_file), so a same-named LICENSE file
    bundled elsewhere in the installed package tree -- e.g. vendored
    third-party code at mypkg/vendor/otherlib/LICENSE -- could be matched
    instead of the real dist-info one, misattributing that library's
    copyright to the dependency. Listed first here specifically to prove
    basename-only matching would have picked it.
    """
    vendored_license = _FakePackagePath(
        "mypkg/vendor/otherlib/LICENSE",
        "Copyright (c) 2015 Vendored Author\n",
    )
    real_license = _FakePackagePath(
        "mypkg-1.0.dist-info/licenses/LICENSE",
        "Copyright (c) 2026 Real Author\n",
    )
    fake_dist = _FakeDistribution([vendored_license, real_license])
    monkeypatch.setattr(deps_originator, "get_pkg_distribution", lambda name: fake_dist)

    meta = _FakeMetadata({}, license_files=["LICENSE"])
    assert _find_license_copyright("mypkg", meta) == "Copyright (c) 2026 Real Author"


def test_find_license_copyright_matches_dist_info_root_not_only_licenses_subdir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    license_file = _FakePackagePath(
        "mypkg-1.0.dist-info/LICENSE.txt",
        "Copyright (c) 2026 Root Dist-Info Author\n",
    )
    fake_dist = _FakeDistribution([license_file])
    monkeypatch.setattr(deps_originator, "get_pkg_distribution", lambda name: fake_dist)

    meta = _FakeMetadata({}, license_files=["LICENSE.txt"])
    assert (
        _find_license_copyright("mypkg", meta)
        == "Copyright (c) 2026 Root Dist-Info Author"
    )


# ---------------------------------------------------------------------------
# PyPI JSON API extraction helpers (pure functions, no network)
# ---------------------------------------------------------------------------


def test_extract_pypi_originator_from_author() -> None:
    info = {"author": "Trail of Bits", "author_email": "opensource@trailofbits.com"}
    assert _extract_pypi_originator(info) == [
        ("Trail of Bits", "opensource@trailofbits.com")
    ]


def test_extract_pypi_originator_falls_back_to_maintainer() -> None:
    info = {
        "maintainer": "Taneli Hukkinen",
        "maintainer_email": "hukkin@users.noreply.github.com",
    }
    assert _extract_pypi_originator(info) == [
        ("Taneli Hukkinen", "hukkin@users.noreply.github.com")
    ]


def test_extract_pypi_originator_absent_returns_none() -> None:
    assert _extract_pypi_originator({}) == []


def test_extract_pypi_license_prefers_license_expression() -> None:
    info = {"license_expression": "MIT", "license": "some legacy free text"}
    assert _extract_pypi_license(info) == "MIT"


def test_extract_pypi_license_falls_back_to_legacy_field() -> None:
    assert _extract_pypi_license({"license": "Apache-2.0"}) == "Apache-2.0"


def test_extract_pypi_license_ignores_implausibly_long_legacy_field() -> None:
    """Regression guard: some PyPI projects paste their entire LICENSE file
    into the free-text ``license`` metadata field -- that must not be
    treated as a short license identifier/expression."""
    info = {"license": "A" * 500}
    assert _extract_pypi_license(info) is None


def test_extract_pypi_license_falls_back_to_classifier() -> None:
    info = {
        "classifiers": [
            "Programming Language :: Python :: 3",
            "License :: OSI Approved :: MIT License",
        ]
    }
    assert _extract_pypi_license(info) == "MIT License"


def test_extract_pypi_license_absent_returns_none() -> None:
    assert _extract_pypi_license({}) is None


def test_extract_release_hash_prefers_wheel() -> None:
    release_info = {
        "urls": [
            {"packagetype": "sdist", "digests": {"sha256": "sdist-hash"}},
            {"packagetype": "bdist_wheel", "digests": {"sha256": "wheel-hash"}},
        ]
    }
    assert _extract_release_hash(release_info) == "wheel-hash"


def test_extract_release_hash_falls_back_to_sdist() -> None:
    release_info = {
        "urls": [{"packagetype": "sdist", "digests": {"sha256": "sdist-hash"}}]
    }
    assert _extract_release_hash(release_info) == "sdist-hash"


def test_extract_release_hash_no_urls_returns_none() -> None:
    assert _extract_release_hash({"urls": []}) is None
    assert _extract_release_hash({}) is None
