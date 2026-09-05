# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for dependency name/version parsing and PURL/installed
enrichment in SPDX 3 SBOMs.

See also: test_deps_enrichment_originator_license.py,
test_deps_enrichment_pypi_fallback.py, test_deps_enrichment_prefetch.py --
this module's siblings, split from the original test_deps_enrichment.py.

Covers two independent causes of "Package identifiers missing" (a
name-parsing bug and a missing no-version PURL fallback) and a
silently-discarded license relationship.
"""

# pylint: disable=protected-access
# pylint: disable=missing-function-docstring

from __future__ import annotations

from importlib.metadata import PackageNotFoundError

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import deps_installed as deps_mod
from pitloom.assemble.spdx3.deps import (
    _enrich_from_installed,
    _parse_dep_name,
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

from .conftest import _FakeMetadata, _make_ci

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
    assert _parse_dep_name("hatchling>=1.32.0") == "hatchling"
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


def test_resolve_version_exact_pin_wins_over_mismatched_installed_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: an exact ``==`` pin (e.g. a resolved ``poetry.lock``
    entry) is authoritative even when a *different* version of the same
    package happens to be installed in Pitloom's own execution
    environment -- that environment has no relationship to the target
    project's environment and must never silently override a real pin."""
    monkeypatch.setattr(deps_mod, "get_package_version", lambda _name: "3.19")

    version, note = _resolve_version("idna", "idna==3.7")

    assert version == "3.7"
    assert note is None


def test_resolve_version_falls_back_to_installed_when_unpinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The installed-environment lookup still applies -- as a fallback --
    for the common case where the constraint doesn't pin an exact version."""
    monkeypatch.setattr(deps_mod, "get_package_version", lambda _name: "2.32.0")

    version, note = _resolve_version("requests", "requests>=2.0")

    assert version == "2.32.0"
    assert note == "Version resolved: Build-time environment (importlib.metadata)"


def test_resolve_version_uses_locked_version_over_installed_when_unpinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per GEMINI.md ("Explicit pin beats local environment"): when a lock
    file pins an exact version for a dependency declared with a range,
    the lock pin is authoritative and Pitloom's host environment is never
    consulted."""
    monkeypatch.setattr(
        deps_mod,
        "get_package_version",
        lambda _name: pytest.fail("host environment should not be consulted"),
    )

    version, note = _resolve_version(
        "requests", "requests>=2.0", locked_version="2.31.0"
    )

    assert version == "2.31.0"
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


def test_add_dependencies_dedupes_same_resolved_name_and_version() -> None:
    """Regression: a package declared under more than one
    ``pyproject.toml`` extra, each split by a ``python_version`` marker
    (e.g. Pitloom's own ``numpy`` under both the ``ai`` and ``numpy``
    extras), used to produce one ``software_Package`` node per raw
    declared string even though they all resolve to the same pinned
    ``(name, version)`` -- duplicate nodes in the emitted SBOM. Declared
    strings that resolve to the same ``(name, version)`` must collapse
    into a single node, with every raw string preserved in its
    provenance comment."""
    doc_uuid = compute_doc_uuid("deduptest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    main_pkg = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="deduptest", doc_uuid=doc_uuid),
        name="deduptest",
        creationInfo=ci,
    )
    exporter.add_package(main_pkg)

    add_dependencies(
        [
            "numpy==2.5.2; python_version<'3.11' and extra == 'ai'",
            "numpy==2.5.2; python_version>='3.11' and extra == 'ai'",
            "numpy==2.5.2; python_version<'3.11' and extra == 'numpy'",
            "numpy==2.5.2; python_version>='3.11' and extra == 'numpy'",
        ],
        "Source: pyproject.toml | Field: project.optional-dependencies",
        require_spdx_id(main_pkg),
        ci,
        "deduptest",
        doc_uuid,
        exporter,
        offline=True,
    )

    packages = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.software_Package)
    ]
    numpy_packages = [p for p in packages if p.name == "numpy"]
    assert len(numpy_packages) == 1

    relationships = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Relationship)
    ]
    depends_on = [
        r
        for r in relationships
        if r.relationshipType == spdx3.RelationshipType.dependsOn
    ]
    assert len(depends_on) == 1

    dep_comment = numpy_packages[0].comment
    assert dep_comment is not None
    assert dep_comment.count("extra == 'ai'") == 2
    assert dep_comment.count("extra == 'numpy'") == 2


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
