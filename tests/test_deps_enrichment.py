# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for dependency-package enrichment in SPDX 3 SBOMs.

Covers four bugs found while reviewing a real published wheel's embedded
SBOM against an NTIA-minimum-elements checker: two independent causes of
"Package identifiers missing" (a name-parsing bug and a missing
no-version PURL fallback), a silently-discarded license relationship, and
a multi-address ``Maintainer-email`` field that a naive parser dropped
entirely. Also covers the PyPI JSON API fallback (used when installed
metadata doesn't cover a field) and the NOASSERTION policy for whatever
neither source can determine.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from typing import Any, cast

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import deps as deps_mod
from pitloom.assemble.spdx3.deps import (
    _add_license_noassertion,
    _enrich_from_installed,
    _extract_pypi_license,
    _extract_pypi_supplier,
    _extract_release_hash,
    _fetch_pypi_release_info,
    _find_license_copyright,
    _parse_dep_name,
    _prefetch_pypi_release_infos,
    _resolve_metadata_url,
    _resolve_supplier,
    _resolve_version,
    add_dependencies,
)
from pitloom.core.models import (
    _clear_doc_counters,
    build_pypi_purl,
    compute_doc_uuid,
    generate_spdx_id,
)
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

_DOC_NAME = "testproject"
_DOC_UUID = compute_doc_uuid("testproject", "1.0", [])


def _make_ci() -> spdx3.CreationInfo:
    ci = spdx3.CreationInfo(
        specVersion="3.0.1",
        created=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    person = spdx3.Person(
        spdxId=generate_spdx_id("Person", doc_name=_DOC_NAME, doc_uuid=_DOC_UUID),
        name="Test",
        creationInfo=ci,
    )
    ci.createdBy = [require_spdx_id(person)]
    return ci


class _FakeMetadata:
    """Minimal stand-in satisfying the ``importlib.metadata.PackageMetadata``
    protocol. ``__getitem__`` returns ``None`` for a missing key at runtime
    (matching the real, ``email.message.Message``-backed implementation,
    which the ``-> str`` protocol signature doesn't accurately capture
    either) -- callers here always guard with ``pkg_meta[field] or ""``,
    same as production code.
    """

    def __init__(
        self,
        fields: dict[str, str],
        project_urls: list[str] | None = None,
        license_files: list[str] | None = None,
    ):
        self._fields = fields
        self._project_urls = project_urls or []
        self._license_files = license_files or []

    def __len__(self) -> int:
        return len(self._fields)

    def __contains__(self, item: str) -> bool:
        return item in self._fields

    def __getitem__(self, key: str) -> str:
        return cast(str, self._fields.get(key))

    def __iter__(self) -> Iterator[str]:
        return iter(self._fields)

    def get_all(self, name: str, failobj: Any = None) -> Any:
        if name == "Project-URL":
            return self._project_urls
        if name == "License-File":
            return self._license_files
        return failobj

    @property
    def json(self) -> dict[str, Any]:
        return dict(self._fields)


# ---------------------------------------------------------------------------
# _parse_dep_name -- environment markers and multi-clause specifiers
# ---------------------------------------------------------------------------


def test_parse_dep_name_strips_environment_marker() -> None:
    """A marker's own ``==`` comparison must not be mistaken for the
    specifier's version operator.

    Regression for the real ``auditwheel>=6.7.0; sys_platform == 'linux'``
    dependency in Pitloom's own ``pyproject.toml``: the old naive split
    checked ``==`` (present in the marker) before ``>=`` in a fixed
    priority order, producing the garbled name
    ``"auditwheel>=6.7.0; sys_platform"``.
    """
    assert _parse_dep_name("auditwheel>=6.7.0; sys_platform == 'linux'") == "auditwheel"


def test_parse_dep_name_strips_python_version_marker() -> None:
    assert _parse_dep_name("tomli>=2.4.1; python_version<'3.11'") == "tomli"


def test_parse_dep_name_handles_multi_clause_specifier() -> None:
    """A later clause's operator must not be matched ahead of an earlier one.

    Regression for the real ``py-spdx-license>=0.0.1,<1`` dependency: after
    ``packaging.Requirement`` normalizes/reorders the specifier set, the old
    fixed-priority substring search matched ``>=`` (checked before ``<``)
    wherever it appeared in the string -- even after the actual first
    operator -- producing the garbled name ``"py-spdx-license<1,"``.
    """
    assert _parse_dep_name("py-spdx-license>=0.0.1,<1") == "py-spdx-license"
    assert _parse_dep_name("pyyaml>=6.0.3,<7") == "pyyaml"


def test_parse_dep_name_plain_specifier_still_works() -> None:
    assert _parse_dep_name("hatchling>=1.31.0") == "hatchling"
    assert _parse_dep_name("numpy==1.24.0") == "numpy"
    assert _parse_dep_name("click") == "click"


# ---------------------------------------------------------------------------
# _resolve_version -- a marker's "==" must not be mistaken for a version pin
# ---------------------------------------------------------------------------


def test_resolve_version_ignores_marker_equality() -> None:
    """Regression: the old ``"==" in dep`` check matched the marker's
    ``sys_platform == 'linux'`` comparison, returning ``"'linux'"`` as the
    "pinned version" for an uninstalled, unpinned dependency."""
    version, note = _resolve_version(
        "not-installed-xyz", "not-installed-xyz>=1.0; sys_platform == 'linux'"
    )
    assert version == "unknown"
    assert note is None


def test_resolve_version_extracts_real_pin() -> None:
    version, note = _resolve_version("not-installed-xyz", "not-installed-xyz==2.5.0")
    assert version == "2.5.0"
    assert note is None


def test_resolve_version_multi_clause_no_pin_is_unknown() -> None:
    version, _ = _resolve_version("not-installed-xyz", "not-installed-xyz>=0.1,<1")
    assert version == "unknown"


def test_resolve_version_extracts_arbitrary_equality_pin() -> None:
    """Regression: the pin-extraction filter only matched operator '==',
    silently excluding PEP 440 arbitrary-equality '===' pins -- a valid,
    parseable specifier that used to resolve to 'unknown' instead of the
    real version."""
    version, note = _resolve_version("not-installed-xyz", "not-installed-xyz===1.0")
    assert version == "1.0"
    assert note is None


def test_resolve_version_falls_back_to_naive_split_for_unparseable_dep() -> None:
    """Regression: a dependency string packaging.Requirement can't parse at
    all used to still recover a best-effort pinned version via a naive
    '==' substring split (pre-Requirement-based parsing); that fallback
    must survive for the genuinely-unparseable case, distinct from the
    marker-false-positive case the Requirement-based path already
    handles correctly on its own."""
    # A stray space makes this invalid PEP 508, but packaging.Requirement
    # not being able to parse it doesn't mean a version can't be recovered.
    version, note = _resolve_version("not installed", "not installed==2.0")
    assert version == "2.0"
    assert note is None


# ---------------------------------------------------------------------------
# build_pypi_purl / add_dependencies -- PURL even without a resolved version
# ---------------------------------------------------------------------------


def test_build_pypi_purl_omits_version_when_none() -> None:
    assert build_pypi_purl("auditwheel", None) == "pkg:pypi/auditwheel"


def test_build_pypi_purl_includes_version_when_known() -> None:
    assert build_pypi_purl("auditwheel", "6.7.0") == "pkg:pypi/auditwheel@6.7.0"


def test_add_dependencies_sets_name_only_purl_for_unresolved_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every dependency must get a PURL, even an unpinned one that isn't
    installed -- a name-only ``pkg:pypi/<name>`` is still a valid,
    matchable identifier, and is strictly better than no identifier at
    all (the reviewer-flagged "Package identifiers missing" gap)."""

    def _raise_not_found(_name: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(deps_mod, "get_package_version", _raise_not_found)
    monkeypatch.setattr(deps_mod, "get_pkg_metadata", _raise_not_found)

    doc_uuid = compute_doc_uuid("purltest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    main_pkg = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="purltest", doc_uuid=doc_uuid),
        name="purltest",
        creationInfo=ci,
    )
    exporter.add_package(main_pkg)

    add_dependencies(
        ["auditwheel>=6.7.0; sys_platform == 'linux'"],
        "Source: pyproject.toml | Field: project.dependencies",
        require_spdx_id(main_pkg),
        ci,
        "purltest",
        doc_uuid,
        exporter,
    )

    packages = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.software_Package)
    ]
    dep = next(p for p in packages if p.name == "auditwheel")
    assert dep.software_packageUrl == "pkg:pypi/auditwheel"
    assert dep.software_packageVersion == "unknown"


# ---------------------------------------------------------------------------
# _enrich_from_installed -- the discarded-concluded-license-relationship bug
# ---------------------------------------------------------------------------


def test_enrich_from_installed_adds_concluded_license_relationship(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: ``build_license_elements`` in single-candidate mode
    returns exactly one of (declared, concluded) depending on whether the
    source is "transparent" -- "installed metadata" isn't, so it always
    returns the *concluded* slot. The caller used to do
    ``rel_declared, _ = build_license_elements(...)``, silently discarding
    that concluded relationship every time -- so no dependency enriched
    from installed metadata ever got a license relationship at all, even
    when ``License-Expression`` was present.
    """
    monkeypatch.setattr(
        deps_mod,
        "get_pkg_metadata",
        lambda name: _FakeMetadata({"License-Expression": "MIT"}),
    )

    doc_uuid = compute_doc_uuid("lictest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    dep_package = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="lictest", doc_uuid=doc_uuid),
        name="tomli",
        creationInfo=ci,
    )
    dep_package.software_packageVersion = "2.4.1"
    exporter.add_package(dep_package)

    _enrich_from_installed("tomli", dep_package, ci, "lictest", doc_uuid, exporter)

    relationships = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Relationship)
    ]
    license_rels = [
        r
        for r in relationships
        if r.from_ == require_spdx_id(dep_package)
        and r.relationshipType
        in (
            spdx3.RelationshipType.hasDeclaredLicense,
            spdx3.RelationshipType.hasConcludedLicense,
        )
    ]
    assert len(license_rels) == 1
    assert (
        license_rels[0].relationshipType == spdx3.RelationshipType.hasConcludedLicense
    )


def test_enrich_from_installed_skips_license_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(deps_mod, "get_pkg_metadata", lambda name: _FakeMetadata({}))

    doc_uuid = compute_doc_uuid("nolictest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    dep_package = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="nolictest", doc_uuid=doc_uuid),
        name="rfc8785",
        creationInfo=ci,
    )
    dep_package.software_packageVersion = "0.1.4"
    exporter.add_package(dep_package)

    _enrich_from_installed("rfc8785", dep_package, ci, "nolictest", doc_uuid, exporter)

    relationships = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Relationship)
    ]
    assert relationships == []


# ---------------------------------------------------------------------------
# _resolve_supplier -- single address, Maintainer fallback, multi-address list
# ---------------------------------------------------------------------------


def test_resolve_supplier_from_author_email() -> None:
    meta = _FakeMetadata({"Author-email": "Trail of Bits <opensource@trailofbits.com>"})
    assert _resolve_supplier(meta) == [("Trail of Bits", "opensource@trailofbits.com")]


def test_resolve_supplier_falls_back_to_maintainer() -> None:
    meta = _FakeMetadata(
        {"Maintainer-email": "Taneli Hukkinen <hukkin@users.noreply.github.com>"}
    )
    assert _resolve_supplier(meta) == [
        (
            "Taneli Hukkinen",
            "hukkin@users.noreply.github.com",
        )
    ]


def test_resolve_supplier_handles_multiple_maintainer_addresses() -> None:
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
    assert _resolve_supplier(meta) == [
        ("Bernát Gábor", "gaborjbernat@gmail.com"),
        ("Kemal Zebari", "kemalzebra@gmail.com"),
        ("Vineet Naik", "naikvin@gmail.com"),
    ]


def test_resolve_supplier_plain_name_no_email() -> None:
    meta = _FakeMetadata({"Author": "Some Org"})
    assert _resolve_supplier(meta) == [("Some Org", None)]


def test_resolve_supplier_absent_returns_none() -> None:
    assert _resolve_supplier(_FakeMetadata({})) == []


def test_enrich_from_installed_sets_supplied_by(
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

    assert dep_package.suppliedBy is not None
    agents = [o for o in exporter.object_set.objects if isinstance(o, spdx3.Person)]
    assert len(agents) == 1
    assert agents[0].name == "Taneli Hukkinen"
    assert dep_package.suppliedBy == require_spdx_id(agents[0])


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
    monkeypatch.setattr(deps_mod, "get_pkg_distribution", lambda name: fake_dist)

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
    monkeypatch.setattr(deps_mod, "get_pkg_distribution", lambda name: fake_dist)

    meta = _FakeMetadata({}, license_files=["LICENSE.txt"])
    assert (
        _find_license_copyright("mypkg", meta)
        == "Copyright (c) 2026 Root Dist-Info Author"
    )


# ---------------------------------------------------------------------------
# PyPI JSON API extraction helpers (pure functions, no network)
# ---------------------------------------------------------------------------


def test_extract_pypi_supplier_from_author() -> None:
    info = {"author": "Trail of Bits", "author_email": "opensource@trailofbits.com"}
    assert _extract_pypi_supplier(info) == [("Trail of Bits", "opensource@trailofbits.com")]


def test_extract_pypi_supplier_falls_back_to_maintainer() -> None:
    info = {
        "maintainer": "Taneli Hukkinen",
        "maintainer_email": "hukkin@users.noreply.github.com",
    }
    assert _extract_pypi_supplier(info) == [("Taneli Hukkinen", "hukkin@users.noreply.github.com")]


def test_extract_pypi_supplier_absent_returns_none() -> None:
    assert _extract_pypi_supplier({}) == []


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


# ---------------------------------------------------------------------------
# _resolve_metadata_url -- deterministic label priority, not hash-order
# ---------------------------------------------------------------------------


def test_resolve_metadata_url_prefers_core_field() -> None:
    assert (
        _resolve_metadata_url("https://core.example", {"home": "https://x"}, ("home",))
        == "https://core.example"
    )


def test_resolve_metadata_url_falls_back_to_first_matching_label_in_order() -> None:
    """Regression: labels used to be a frozenset, so which of several
    matching Project-URL labels won was dependent on Python's per-process
    string-hash randomization (PYTHONHASHSEED) rather than a fixed
    priority -- breaking build-to-build SBOM reproducibility. Verified
    empirically that a frozenset of these exact three strings iterates in
    different orders across different hash seeds; a tuple does not."""
    project_urls = {"home": "https://a.example", "homepage": "https://b.example"}
    assert (
        _resolve_metadata_url("", project_urls, ("homepage", "home page", "home"))
        == "https://b.example"
    )
    assert (
        _resolve_metadata_url("", project_urls, ("home", "home page", "homepage"))
        == "https://a.example"
    )


def test_resolve_metadata_url_none_when_nothing_matches() -> None:
    assert _resolve_metadata_url("", {}, ("homepage", "home")) is None
    assert _resolve_metadata_url("UNKNOWN", {}, ("homepage", "home")) is None


# ---------------------------------------------------------------------------
# add_dependencies -- PyPI fallback integration, NOASSERTION policy, offline
# ---------------------------------------------------------------------------


def _uninstalled(*_args: object, **_kwargs: object) -> None:
    raise PackageNotFoundError


def test_add_dependencies_pypi_fallback_fills_gaps_and_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a dependency isn't installed locally, offline=False must reach
    the PyPI JSON API for supplier/license/hash, and never assert
    NOASSERTION for fields that lookup actually filled."""
    monkeypatch.setattr(deps_mod, "get_package_version", _uninstalled)
    monkeypatch.setattr(deps_mod, "get_pkg_metadata", _uninstalled)
    monkeypatch.setattr(
        deps_mod,
        "_fetch_pypi_release_info",
        lambda name, version: {
            "info": {
                "author": "Some Author",
                "author_email": "author@example.com",
                "license_expression": "MIT",
            },
            "urls": [
                {"packagetype": "bdist_wheel", "digests": {"sha256": "deadbeef" * 8}},
            ],
        },
    )

    doc_uuid = compute_doc_uuid("pypitest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    main_pkg = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="pypitest", doc_uuid=doc_uuid),
        name="pypitest",
        creationInfo=ci,
    )
    exporter.add_package(main_pkg)

    add_dependencies(
        ["somepkg==2.0.0"],
        "Source: pyproject.toml | Field: project.dependencies",
        require_spdx_id(main_pkg),
        ci,
        "pypitest",
        doc_uuid,
        exporter,
        offline=False,
    )

    packages = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.software_Package)
    ]
    dep = next(p for p in packages if p.name == "somepkg")

    # PyPI's JSON API has no "copyright" field at all, so this correctly
    # still falls back to NOASSERTION even though supplier/license/hash
    # were all filled from the network.
    assert dep.software_copyrightText == "NOASSERTION"
    verified = dep.verifiedUsing[0]
    assert isinstance(verified, spdx3.Hash)
    assert verified.hashValue == "deadbeef" * 8

    agents = [o for o in exporter.object_set.objects if isinstance(o, spdx3.Person)]
    assert agents[0].name == "Some Author"

    relationships = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Relationship)
    ]
    license_rels = [
        r
        for r in relationships
        if r.from_ == require_spdx_id(dep)
        and r.relationshipType
        in (
            spdx3.RelationshipType.hasDeclaredLicense,
            spdx3.RelationshipType.hasConcludedLicense,
        )
    ]
    assert len(license_rels) == 1
    licenses = [
        o
        for o in exporter.object_set.objects
        if isinstance(o, spdx3.simplelicensing_SimpleLicensingText)
    ]
    assert any(lic.simplelicensing_licenseText == "MIT" for lic in licenses)


def test_add_dependencies_noassertion_when_nothing_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dependency with no local metadata and no PyPI hit must still get
    an explicit NOASSERTION copyright and license, not silently absent
    fields."""
    monkeypatch.setattr(deps_mod, "get_package_version", _uninstalled)
    monkeypatch.setattr(deps_mod, "get_pkg_metadata", _uninstalled)
    monkeypatch.setattr(
        deps_mod, "_fetch_pypi_release_info", lambda name, version: None
    )

    doc_uuid = compute_doc_uuid("noassertion", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    main_pkg = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="noassertion", doc_uuid=doc_uuid),
        name="noassertion",
        creationInfo=ci,
    )
    exporter.add_package(main_pkg)

    add_dependencies(
        ["totallyunknownpkg>=1.0"],
        "Source: pyproject.toml | Field: project.dependencies",
        require_spdx_id(main_pkg),
        ci,
        "noassertion",
        doc_uuid,
        exporter,
        offline=False,
    )

    packages = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.software_Package)
    ]
    dep = next(p for p in packages if p.name == "totallyunknownpkg")
    assert dep.software_copyrightText == "NOASSERTION"
    assert not dep.verifiedUsing

    relationships = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Relationship)
    ]
    license_rels = [
        r
        for r in relationships
        if r.from_ == require_spdx_id(dep)
        and r.relationshipType == spdx3.RelationshipType.hasDeclaredLicense
    ]
    assert len(license_rels) == 1
    licenses = [
        o
        for o in exporter.object_set.objects
        if isinstance(o, spdx3.simplelicensing_SimpleLicensingText)
    ]
    noassertion_licenses = [
        lic for lic in licenses if lic.simplelicensing_licenseText == "NOASSERTION"
    ]
    assert len(noassertion_licenses) == 1
    assert license_rels[0].to == [require_spdx_id(noassertion_licenses[0])]


def test_add_dependencies_offline_skips_pypi_entirely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(deps_mod, "get_package_version", _uninstalled)
    monkeypatch.setattr(deps_mod, "get_pkg_metadata", _uninstalled)

    called = False

    def _fail_if_called(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(deps_mod, "_fetch_pypi_release_info", _fail_if_called)

    doc_uuid = compute_doc_uuid("offlinetest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    main_pkg = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="offlinetest", doc_uuid=doc_uuid),
        name="offlinetest",
        creationInfo=ci,
    )
    exporter.add_package(main_pkg)

    add_dependencies(
        ["somepkg>=1.0"],
        "Source: pyproject.toml | Field: project.dependencies",
        require_spdx_id(main_pkg),
        ci,
        "offlinetest",
        doc_uuid,
        exporter,
        offline=True,
    )

    assert called is False
    packages = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.software_Package)
    ]
    dep = next(p for p in packages if p.name == "somepkg")
    assert dep.software_copyrightText == "NOASSERTION"


def test_add_license_noassertion_is_deduped() -> None:
    """Two packages that both fall back to NOASSERTION must share one
    license element, not mint a duplicate for each."""
    doc_uuid = compute_doc_uuid("noassertiondedup", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()

    for name in ("pkg-a", "pkg-b"):
        dep_package = spdx3.software_Package(
            spdxId=generate_spdx_id(
                "Package", doc_name="noassertiondedup", doc_uuid=doc_uuid
            ),
            name=name,
            creationInfo=ci,
        )
        exporter.add_package(dep_package)
        _add_license_noassertion(
            dep_package, ci, "noassertiondedup", doc_uuid, exporter
        )

    licenses = [
        o
        for o in exporter.object_set.objects
        if isinstance(o, spdx3.simplelicensing_SimpleLicensingText)
    ]
    noassertion_licenses = [
        lic for lic in licenses if lic.simplelicensing_licenseText == "NOASSERTION"
    ]
    assert len(noassertion_licenses) == 1


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

    monkeypatch.setattr(deps_mod, "_fetch_pypi_release_info", _slow_fetch)

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

    monkeypatch.setattr(deps_mod, "_fetch_pypi_release_info", _counting_fetch)

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

    monkeypatch.setattr(deps_mod, "_fetch_pypi_release_info", _record_fetch)

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

    monkeypatch.setattr(deps_mod, "_fetch_pypi_release_info", _counting_fetch)

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
    assert deps_mod._resolve_supplier(meta) == [
        ("Alice", None),
        ("Bob", None),
        ("Charlie", None),
    ]


def test_apply_supplier_creates_others_external_ref() -> None:
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

    suppliers = [("Alice", None), ("Others (See OTHER_AUTHORS.md)", None)]
    deps_mod._apply_supplier(
        suppliers,
        dep_package,
        ci,
        "otherstest",
        doc_uuid,
        exporter,
        repo_url="https://github.com/foo/bar.git",
        offline=True,
    )

    agents = [o for o in exporter.object_set.objects if isinstance(o, spdx3.Person)]
    assert len(agents) == 2
    
    others = next((a for a in agents if "Others" in a.name), None)
    assert others is not None
    assert len(others.externalRef) == 1
    ref = others.externalRef[0]
    assert ref.externalRefType == spdx3.ExternalRefType.documentation
    assert ref.locator == ["https://github.com/foo/bar/blob/HEAD/OTHER_AUTHORS.md"]
    assert ref.comment == "Refers to OTHER_AUTHORS.md"
