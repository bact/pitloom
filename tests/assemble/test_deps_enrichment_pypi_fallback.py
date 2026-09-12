# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for the PyPI JSON API fallback path in
``pitloom.assemble.spdx3.deps.add_dependencies``.

See also: test_deps_enrichment_names_versions.py,
test_deps_enrichment_originator_license.py, test_deps_enrichment_prefetch.py --
this module's siblings, split from the original test_deps_enrichment.py.
test_deps_license.py holds the deps_license.py unit tests split out of
this file.

Covers the PyPI JSON API fallback (used when installed metadata doesn't
cover a field) and the NOASSERTION policy for whatever neither source can
determine.
"""

# pylint: disable=protected-access
# pylint: disable=missing-function-docstring

from __future__ import annotations

from importlib.metadata import PackageNotFoundError

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import deps_installed as deps_mod
from pitloom.assemble.spdx3 import deps_pypi
from pitloom.assemble.spdx3.deps import _enrich_from_pypi, add_dependencies
from pitloom.assemble.spdx3.deps_license import _add_license_noassertion
from pitloom.assemble.spdx3.deps_originator import _resolve_metadata_url
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid, generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

from .conftest import _make_ci

_real_fetch_pypi = deps_pypi._fetch_pypi_release_info

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
        deps_pypi,
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
        deps_pypi, "_fetch_pypi_release_info", lambda name, version: None
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

    monkeypatch.setattr(deps_pypi, "_fetch_pypi_release_info", _fail_if_called)

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
    assert not dep.verifiedUsing


def test_add_dependencies_offline_populates_hash_from_lock_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unlike a PyPI-looked-up hash, a lock-file hash is available even
    with offline=True -- see lock-hash-preservation.md."""
    monkeypatch.setattr(deps_mod, "get_package_version", _uninstalled)
    monkeypatch.setattr(deps_mod, "get_pkg_metadata", _uninstalled)
    monkeypatch.setattr(deps_pypi, "_fetch_pypi_release_info", _uninstalled)

    lock_hash = "c" * 64
    doc_uuid = compute_doc_uuid("offlinehashtest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    main_pkg = spdx3.software_Package(
        spdxId=generate_spdx_id(
            "Package", doc_name="offlinehashtest", doc_uuid=doc_uuid
        ),
        name="offlinehashtest",
        creationInfo=ci,
    )
    exporter.add_package(main_pkg)

    add_dependencies(
        ["somepkg==2.0.0"],
        "Source: pyproject.toml | Field: project.dependencies",
        require_spdx_id(main_pkg),
        ci,
        "offlinehashtest",
        doc_uuid,
        exporter,
        offline=True,
        locked_hashes={"somepkg": lock_hash},
    )

    packages = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.software_Package)
    ]
    dep = next(p for p in packages if p.name == "somepkg")
    verified = dep.verifiedUsing[0]
    assert isinstance(verified, spdx3.Hash)
    assert verified.hashValue == lock_hash


def test_add_dependencies_locked_hashes_given_but_no_entry_for_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`locked_hashes` covering unrelated packages (but not this one) must
    leave `verifiedUsing` unset, not raise or apply an unrelated hash."""
    monkeypatch.setattr(deps_mod, "get_package_version", _uninstalled)
    monkeypatch.setattr(deps_mod, "get_pkg_metadata", _uninstalled)
    monkeypatch.setattr(deps_pypi, "_fetch_pypi_release_info", _uninstalled)

    doc_uuid = compute_doc_uuid("nomatchhashtest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    main_pkg = spdx3.software_Package(
        spdxId=generate_spdx_id(
            "Package", doc_name="nomatchhashtest", doc_uuid=doc_uuid
        ),
        name="nomatchhashtest",
        creationInfo=ci,
    )
    exporter.add_package(main_pkg)

    add_dependencies(
        ["somepkg==2.0.0"],
        "Source: pyproject.toml | Field: project.dependencies",
        require_spdx_id(main_pkg),
        ci,
        "nomatchhashtest",
        doc_uuid,
        exporter,
        offline=True,
        locked_hashes={"unrelated-package": "d" * 64},
    )

    packages = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.software_Package)
    ]
    dep = next(p for p in packages if p.name == "somepkg")
    assert not dep.verifiedUsing


def test_add_dependencies_lock_hash_wins_over_pypi_hash_online(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lock-file hash always takes priority over a PyPI JSON API hash,
    even online -- the lock file names the exact resolved artifact,
    which is more authoritative than a PyPI lookup that could resolve to
    a different release build. See lock-hash-preservation.md."""
    monkeypatch.setattr(deps_mod, "get_package_version", _uninstalled)
    monkeypatch.setattr(deps_mod, "get_pkg_metadata", _uninstalled)
    monkeypatch.setattr(
        deps_pypi,
        "_fetch_pypi_release_info",
        lambda name, version: {
            "info": {},
            "urls": [
                {"packagetype": "bdist_wheel", "digests": {"sha256": "b" * 64}},
            ],
        },
    )

    lock_hash = "c" * 64
    doc_uuid = compute_doc_uuid("lockwinstest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    main_pkg = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="lockwinstest", doc_uuid=doc_uuid),
        name="lockwinstest",
        creationInfo=ci,
    )
    exporter.add_package(main_pkg)

    add_dependencies(
        ["somepkg==2.0.0"],
        "Source: pyproject.toml | Field: project.dependencies",
        require_spdx_id(main_pkg),
        ci,
        "lockwinstest",
        doc_uuid,
        exporter,
        offline=False,
        locked_hashes={"somepkg": lock_hash},
    )

    packages = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.software_Package)
    ]
    dep = next(p for p in packages if p.name == "somepkg")
    verified = dep.verifiedUsing[0]
    assert isinstance(verified, spdx3.Hash)
    assert verified.hashValue == lock_hash


def test_add_dependencies_lock_hash_skipped_on_declared_pin_version_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: a declared exact pin conflicting with the lock's
    resolved version must win the version (per "explicit pin beats lock"),
    and the lock's hash -- which describes the *locked* version's
    artifact, not the declared one -- must not be attached to a package
    now recorded at a different version."""
    monkeypatch.setattr(deps_mod, "get_package_version", _uninstalled)
    monkeypatch.setattr(deps_mod, "get_pkg_metadata", _uninstalled)
    monkeypatch.setattr(deps_pypi, "_fetch_pypi_release_info", _uninstalled)

    doc_uuid = compute_doc_uuid("pinconflicthashtest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    main_pkg = spdx3.software_Package(
        spdxId=generate_spdx_id(
            "Package", doc_name="pinconflicthashtest", doc_uuid=doc_uuid
        ),
        name="pinconflicthashtest",
        creationInfo=ci,
    )
    exporter.add_package(main_pkg)

    add_dependencies(
        ["somepkg==2.0.0"],
        "Source: pyproject.toml | Field: project.dependencies",
        require_spdx_id(main_pkg),
        ci,
        "pinconflicthashtest",
        doc_uuid,
        exporter,
        offline=True,
        locked_versions={"somepkg": "1.0.0"},
        locked_hashes={"somepkg": "e" * 64},
    )

    packages = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.software_Package)
    ]
    dep = next(p for p in packages if p.name == "somepkg")
    assert dep.software_packageVersion == "2.0.0"
    assert not dep.verifiedUsing


def test_add_dependencies_lock_hash_skipped_when_name_absent_from_locked_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: `locked_hashes` covering a name that `locked_versions`
    doesn't (e.g. excluded upstream as a genuine locked-version conflict,
    or never lock-resolved at all) must not attach that hash -- there is
    no verified version match to trust it against."""
    monkeypatch.setattr(deps_mod, "get_package_version", _uninstalled)
    monkeypatch.setattr(deps_mod, "get_pkg_metadata", _uninstalled)
    monkeypatch.setattr(deps_pypi, "_fetch_pypi_release_info", _uninstalled)

    doc_uuid = compute_doc_uuid("noversionhashtest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    main_pkg = spdx3.software_Package(
        spdxId=generate_spdx_id(
            "Package", doc_name="noversionhashtest", doc_uuid=doc_uuid
        ),
        name="noversionhashtest",
        creationInfo=ci,
    )
    exporter.add_package(main_pkg)

    add_dependencies(
        ["somepkg==2.0.0"],
        "Source: pyproject.toml | Field: project.dependencies",
        require_spdx_id(main_pkg),
        ci,
        "noversionhashtest",
        doc_uuid,
        exporter,
        offline=True,
        locked_versions={},
        locked_hashes={"somepkg": "f" * 64},
    )

    packages = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.software_Package)
    ]
    dep = next(p for p in packages if p.name == "somepkg")
    assert not dep.verifiedUsing


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
# _fetch_pypi_release_info -- URL construction and failure handling
# ---------------------------------------------------------------------------


def test_fetch_pypi_release_info_versioned_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_fetch_json(url: str, *, timeout: float) -> dict[str, object]:
        captured["url"] = url
        captured["timeout"] = timeout
        return {"info": {}}

    monkeypatch.setattr(deps_pypi, "_fetch_pypi_release_info", _real_fetch_pypi)
    monkeypatch.setattr(deps_pypi, "fetch_json", _fake_fetch_json)
    result = deps_pypi._fetch_pypi_release_info("requests", "2.31.0")
    assert captured["url"] == "https://pypi.org/pypi/requests/2.31.0/json"
    assert result == {"info": {}}


def test_fetch_pypi_release_info_unversioned_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_fetch_json(url: str, *, timeout: float) -> dict[str, object]:
        del timeout
        captured["url"] = url
        return {"info": {}}

    monkeypatch.setattr(deps_pypi, "_fetch_pypi_release_info", _real_fetch_pypi)
    monkeypatch.setattr(deps_pypi, "fetch_json", _fake_fetch_json)
    deps_pypi._fetch_pypi_release_info("requests", None)
    assert captured["url"] == "https://pypi.org/pypi/requests/json"


def test_fetch_pypi_release_info_returns_none_on_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(url: str, *, timeout: float) -> dict[str, object]:
        del url, timeout
        raise ValueError("network error")

    monkeypatch.setattr(deps_pypi, "_fetch_pypi_release_info", _real_fetch_pypi)
    monkeypatch.setattr(deps_pypi, "fetch_json", _raise)
    assert deps_pypi._fetch_pypi_release_info("requests", None) is None


# ---------------------------------------------------------------------------
# _enrich_from_pypi -- repo_url-already-present and unknown-version branches
# ---------------------------------------------------------------------------


def test_enrich_from_pypi_repo_url_present_skips_home_page_fallback() -> None:
    """When ``project_urls`` already yields a repository URL, the
    ``home_page`` fallback lookup is skipped entirely (branch: ``repo_url``
    truthy). No license fields are present either, exercising the
    "license lookup found nothing" branch in the same call."""
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    dep_pkg = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="repourltest", doc_uuid="u"),
        name="pkgx",
        creationInfo=ci,
    )
    release_info = {
        "info": {
            "project_urls": {"Repository": "https://github.com/example/pkgx"},
            "home_page": "https://should-not-be-consulted.example",
        },
        "urls": [],
    }
    filled = _enrich_from_pypi(
        "pkgx",
        "1.0.0",
        dep_pkg,
        ci,
        "repourltest",
        "u",
        exporter,
        already_filled=set(),
        release_info_cache={("pkgx", "1.0.0"): release_info},
    )
    assert "license" not in filled
    assert "hash" not in filled


def test_enrich_from_pypi_unknown_version_skips_hash_extraction() -> None:
    """``dep_version == "unknown"`` resolves to ``version=None``, which
    skips the release-hash extraction entirely (branch: ``version is
    None``), even though the release info carries a hash."""
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    dep_pkg = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="unkverstest", doc_uuid="u"),
        name="pkgy",
        creationInfo=ci,
    )
    release_info = {
        "info": {"license_expression": "MIT"},
        "urls": [{"packagetype": "bdist_wheel", "digests": {"sha256": "abc123"}}],
    }
    filled = _enrich_from_pypi(
        "pkgy",
        "unknown",
        dep_pkg,
        ci,
        "unkverstest",
        "u",
        exporter,
        already_filled=set(),
        release_info_cache={("pkgy", None): release_info},
    )
    assert "hash" not in filled
    assert not dep_pkg.verifiedUsing
