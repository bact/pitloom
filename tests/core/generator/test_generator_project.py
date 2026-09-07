# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.assemble.generate_project_sbom / build(): basic
generation, main-package PURL, output path, and content-type method validation.

See also:
- :mod:`tests.core.generator.test_generator_project_creators` for
  creators and tool handling.
- :mod:`tests.core.generator.test_generator_project_structure` for
  structure and dependencies.
- :mod:`tests.core.generator.test_generator_project_enrichment` for
  project-level enrichment.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone, tzinfo
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3.document import _build_main_package, _magika_version, build
from pitloom.core.creation import CreationMetadata, Creator
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectFile, ProjectMetadata
from tests.assemble.conftest import _FakeMetadata


def test_generate_project_sbom_basic() -> None:
    """Test basic SBOM generation from a simple project."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "test-package"
version = "1.0.0"
description = "A test package"
dependencies = ["requests>=2.28.0", "numpy==1.24.0"]

[project.urls]
Homepage = "https://example.com"
Source = "https://github.com/test/test-package"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        sbom_json = generate_project_sbom(
            tmppath,
            creation_metadata=CreationMetadata(
                creators=[Creator(name="Test Creator", email="test@example.com")],
            ),
        )

        # Parse and validate JSON
        sbom_data = json.loads(sbom_json)

        # Check basic structure
        assert "@context" in sbom_data
        assert "@graph" in sbom_data
        assert sbom_data["@context"] == "https://spdx.org/rdf/3.0.1/spdx-context.jsonld"

        graph = sbom_data["@graph"]
        assert len(graph) > 0

        # Check for required elements
        element_types = {elem["type"] for elem in graph}
        assert "CreationInfo" in element_types
        assert "Person" in element_types
        assert "software_Package" in element_types
        assert "software_Sbom" in element_types
        assert "SpdxDocument" in element_types

        # Check package details
        packages = [elem for elem in graph if elem["type"] == "software_Package"]
        main_package = [p for p in packages if p["name"] == "test-package"][0]
        assert main_package["software_packageVersion"] == "1.0.0"

        # Check dependencies
        dep_packages = [p for p in packages if p["name"] in ["requests", "numpy"]]
        assert len(dep_packages) >= 2


def test_generate_project_sbom_basic_main_package_purl() -> None:
    """The main package must carry a pkg:pypi PURL when a real version is known."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "test-package"
version = "1.0.0"
description = "A test package"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        sbom_json = generate_project_sbom(tmppath)
        graph = json.loads(sbom_json)["@graph"]

        packages = [e for e in graph if e.get("type") == "software_Package"]
        main_package = next(p for p in packages if p["name"] == "test-package")
        assert main_package["software_packageUrl"] == "pkg:pypi/test-package@1.0.0"


def test_generate_project_sbom_invalid_content_type_method_raises() -> None:
    """An explicit content_type_method outside auto/magika/extension must
    raise immediately, matching the TOML/CLI paths' own validation --
    not silently fall through to guess_content_type's "auto" behavior."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "test-package"
version = "1.0.0"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        with pytest.raises(ValueError, match="content_type_method must be one of"):
            generate_project_sbom(tmppath, content_type_method="mimetypes")


def test_build_main_package_no_purl_without_real_version() -> None:
    """No PURL is set when the version is unknown."""
    project = ProjectMetadata(name="no-version-project")
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = [e for e in graph if e.get("type") == "software_Package"]
    main_package = next(p for p in packages if p["name"] == "no-version-project")
    assert "software_packageUrl" not in main_package


def test_build_main_package_purl_normalizes_name() -> None:
    """PURL name is lowercased with underscores replaced by hyphens."""
    project = ProjectMetadata(name="My_Package", version="2.0.0")
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = [e for e in graph if e.get("type") == "software_Package"]
    main_package = next(p for p in packages if p["name"] == "My_Package")
    assert main_package["software_packageUrl"] == "pkg:pypi/my-package@2.0.0"


def test_build_main_package_copyright_year_fallback_when_created_not_datetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When spdx_ci.created is not a datetime, fall back to current UTC year."""

    class MockDatetime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> MockDatetime:
            return cls(2026, 3, 15, 12, 0, tzinfo=timezone.utc)

    monkeypatch.setattr("pitloom.assemble.spdx3.document.datetime", MockDatetime)
    project = ProjectMetadata(name="fallback-year-pkg")
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())
    spdx_ci = MagicMock(spec=spdx3.CreationInfo)
    spdx_ci.created = None
    pkg = _build_main_package(doc, spdx_ci, [], "00000000-0000-0000-0000-000000000000")
    assert pkg.software_copyrightText is not None
    assert "Copyright (c) 2026" in pkg.software_copyrightText


def test_magika_version_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """_magika_version() must only hit importlib.metadata once per process."""
    _magika_version.cache_clear()
    call_count = 0

    # pylint: disable=unused-argument

    def _fake_pkg_version(name: str) -> str:
        nonlocal call_count
        call_count += 1
        return "1.2.3"

    monkeypatch.setattr(
        "pitloom.assemble.spdx3._document_files._pkg_version", _fake_pkg_version
    )

    assert _magika_version() == "1.2.3"
    assert _magika_version() == "1.2.3"
    assert _magika_version() == "1.2.3"
    assert call_count == 1
    _magika_version.cache_clear()


def test_generate_project_sbom_to_output_path() -> None:
    """Test SBOM generation written to an output file."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "simple-app"
version = "0.5.0"
description = "A simple application"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        output_path = tmppath / "sbom.spdx3.json"
        generate_project_sbom(tmppath, output_path=output_path)

        assert output_path.exists()

        # Validate the file content
        sbom_data = json.loads(output_path.read_text())
        assert "@context" in sbom_data
        assert "@graph" in sbom_data


def test_build_main_package_concluded_only_license_skips_declared_relationship() -> (
    None
):
    """When the main package's only license candidate is classified as
    *concluded* (single-candidate mode, no ``license_concluded`` set --
    e.g. detected from a LICENSE file rather than declared in
    pyproject.toml), ``build_license_elements`` returns ``(None,
    rel_concluded)``. ``build()`` must skip adding the (absent) declared
    relationship without error, and still add the concluded one."""
    project = ProjectMetadata(
        name="concludedonly",
        version="1.0.0",
        license_name="MIT",
        provenance={"license": "Source: LICENSE file"},
    )
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    exporter = build(doc)

    relationships = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Relationship)
    ]
    license_rels = [
        r
        for r in relationships
        if r.relationshipType
        in (
            spdx3.RelationshipType.hasDeclaredLicense,
            spdx3.RelationshipType.hasConcludedLicense,
        )
        and r.from_
        in {
            p.spdxId
            for p in exporter.object_set.objects
            if isinstance(p, spdx3.software_Package) and p.name == "concludedonly"
        }
    ]
    assert len(license_rels) == 1
    assert (
        license_rels[0].relationshipType == spdx3.RelationshipType.hasConcludedLicense
    )


def test_magika_version_falls_back_to_unknown_when_package_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_magika_version() must fall back to "unknown" when ``magika`` isn't
    installed (importlib.metadata.version() raises PackageNotFoundError)."""
    _magika_version.cache_clear()

    def _raise_not_found(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(
        "pitloom.assemble.spdx3._document_files._pkg_version", _raise_not_found
    )

    assert _magika_version() == "unknown"
    _magika_version.cache_clear()


def test_add_package_files_skips_relationships_when_build_relationship_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both the directory-containment and file-containment "contains"
    Relationship elements must be skipped -- not added -- when
    build_relationship() returns None, rather than crashing."""
    monkeypatch.setattr(
        "pitloom.assemble.spdx3._document_files.build_relationship",
        lambda *args, **kwargs: None,
    )
    files = [
        ProjectFile(
            physical_path="src/pkg/module.py",
            distribution_path="pkg/module.py",
            digest_sha256="a" * 64,
        ),
    ]
    project = ProjectMetadata(name="rel-none-project", version="1.0.0", files=files)
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    contains_rels = [
        e
        for e in graph
        if e.get("type") == "Relationship" and e.get("relationshipType") == "contains"
    ]
    assert contains_rels == []


def test_build_document_ai_model_license_adds_simple_licensing_profile() -> None:
    """When an AI model has a license and the project has no license,
    simpleLicensing profile must be added to profileConformance."""
    from pitloom.core.ai_metadata import AiModelMetadata

    project = ProjectMetadata(name="ai-lic-project", version="1.0.0", license_name=None)
    ai_model = AiModelMetadata(name="test-model", license="Apache-2.0")
    doc = DocumentModel(
        project=project,
        creation_metadata=CreationMetadata(),
        ai_models=[ai_model],
    )
    exporter = build(doc, offline=True)
    spdx_doc = next(
        o for o in exporter.object_set.objects if isinstance(o, spdx3.SpdxDocument)
    )
    assert spdx3.ProfileIdentifierType.ai in spdx_doc.profileConformance
    assert spdx3.ProfileIdentifierType.simpleLicensing in spdx_doc.profileConformance


def test_build_concluded_license_without_declared_license() -> None:
    """When license_name is None but license_concluded is present,
    concluded license relationship must be emitted and simpleLicensing added."""
    project = ProjectMetadata(
        name="concluded-only",
        version="1.0.0",
        license_name=None,
        license_concluded="MIT",
    )
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())
    exporter = build(doc, offline=True)
    graph = json.loads(exporter.to_json())["@graph"]

    spdx_doc = next(e for e in graph if e.get("type") == "SpdxDocument")
    assert "simpleLicensing" in spdx_doc["profileConformance"]

    rels = [e for e in graph if e.get("type") == "Relationship"]
    concluded_rels = [
        r for r in rels if r.get("relationshipType") == "hasConcludedLicense"
    ]
    assert len(concluded_rels) == 1
    licenses = {
        e["spdxId"]: e.get("simplelicensing_licenseText")
        for e in graph
        if e.get("type") == "simplelicensing_SimpleLicensingText"
    }
    assert licenses[concluded_rels[0]["to"][0]] == "MIT"


def test_generate_project_sbom_does_not_mutate_caller_files(
    tmp_path: Path,
) -> None:
    """generate_project_sbom must not mutate caller's files list in place."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "caller-name"\nversion = "1.0.0"\n'
    )
    initial_files: list[ProjectFile] = []
    caller_meta = ProjectMetadata(
        name="caller-name",
        version="1.0.0",
        files=initial_files,
    )
    from pitloom.core.config import PitloomConfig

    generate_project_sbom(
        tmp_path, project_metadata=caller_meta, pitloom_config=PitloomConfig()
    )
    assert initial_files == []


def test_build_dependency_license_adds_simple_licensing_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a dependency has a resolved license, simpleLicensing must be in
    profileConformance.
    """
    fake_meta = _FakeMetadata(
        {
            "Name": "requests",
            "Version": "2.31.0",
            "License": "Apache-2.0",
        }
    )
    monkeypatch.setattr(
        "pitloom.assemble.spdx3.deps_installed.get_pkg_metadata",
        lambda _name: fake_meta,
    )
    project = ProjectMetadata(
        name="nolicense-with-dep",
        version="1.0.0",
        license_name=None,
        dependencies=["requests==2.31.0"],
    )
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())
    exporter = build(doc, offline=True)
    spdx_doc = next(
        o for o in exporter.object_set.objects if isinstance(o, spdx3.SpdxDocument)
    )
    assert spdx3.ProfileIdentifierType.simpleLicensing in spdx_doc.profileConformance
