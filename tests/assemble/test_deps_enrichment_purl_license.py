# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for a dependency's PURL without a resolved version and
its concluded licence from installed metadata in SPDX 3 SBOMs.

See also: tests/assemble/test_deps_enrichment_names_versions.py (name and version
parsing).
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
# build_pypi_purl / add_dependencies -- PURL even without a resolved version
# ---------------------------------------------------------------------------


def test_build_pypi_purl_omits_version_when_none() -> None:
    assert build_pypi_purl("auditwheel", None) == "pkg:pypi/auditwheel"


def test_build_pypi_purl_includes_version_when_known() -> None:
    assert build_pypi_purl("auditwheel", "6.7.0") == "pkg:pypi/auditwheel@6.7.0"
    assert build_pypi_purl("torch", "2.0.0+cpu") == "pkg:pypi/torch@2.0.0%2Bcpu"


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
    # One edge, optional: every declared string is gated by an extra.
    assert [
        (type(r), r.relationshipType, r.comment)
        for r in relationships
        if r.relationshipType == spdx3.RelationshipType.hasOptionalDependency
    ] == [
        (
            spdx3.Relationship,
            spdx3.RelationshipType.hasOptionalDependency,
            "extras: ai, numpy",
        )
    ]

    dep_comment = numpy_packages[0].comment
    assert dep_comment is not None
    assert dep_comment.count("extra == 'ai'") == 2
    assert dep_comment.count("extra == 'numpy'") == 2


def test_add_dependencies_dedupes_case_insensitive_name() -> None:
    """Dependencies declared with differing case (e.g. Django vs django)
    at the same version must collapse into a single software_Package node,
    preserving the first-seen raw name."""
    doc_uuid = compute_doc_uuid("casetest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    main_pkg = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="casetest", doc_uuid=doc_uuid),
        name="casetest",
        creationInfo=ci,
    )
    exporter.add_package(main_pkg)

    add_dependencies(
        ["Django==4.2.1", "django==4.2.1"],
        "Source: pyproject.toml | Field: project.dependencies",
        require_spdx_id(main_pkg),
        ci,
        "casetest",
        doc_uuid,
        exporter,
        offline=True,
    )

    packages = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.software_Package)
    ]
    django_packages = [p for p in packages if p.name in ("Django", "django")]
    assert len(django_packages) == 1
    assert django_packages[0].name == "Django"


def test_add_dependencies_dedupes_separator_canonicalization() -> None:
    """Dependencies declared with differing separators (e.g. pydantic-core vs
    pydantic_core) at the same version must collapse into a single
    software_Package node, preserving the first-seen raw name."""
    doc_uuid = compute_doc_uuid("sepcanonical", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    main_pkg = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="sepcanonical", doc_uuid=doc_uuid),
        name="sepcanonical",
        creationInfo=ci,
    )
    exporter.add_package(main_pkg)

    add_dependencies(
        ["pydantic-core==1.0.0", "pydantic_core==1.0.0"],
        "Source: pyproject.toml | Field: project.dependencies",
        require_spdx_id(main_pkg),
        ci,
        "sepcanonical",
        doc_uuid,
        exporter,
        offline=True,
    )

    packages = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.software_Package)
    ]
    pydantic_packages = [
        p for p in packages if p.name in ("pydantic-core", "pydantic_core")
    ]
    assert len(pydantic_packages) == 1
    assert pydantic_packages[0].name == "pydantic-core"

    depends_on_rels = [
        o
        for o in exporter.object_set.objects
        if isinstance(o, spdx3.Relationship)
        and o.relationshipType == spdx3.RelationshipType.dependsOn
        and require_spdx_id(pydantic_packages[0]) in o.to
    ]
    assert len(depends_on_rels) == 1


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
