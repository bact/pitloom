# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.assemble.generate_project_sbom / build(): basic
generation, main-package PURL, output path, and content-type method validation.

See also:
- :mod:`tests.core.test_generator_project_creators` for creators and tool handling.
- :mod:`tests.core.test_generator_project_structure` for structure and dependencies.
- :mod:`tests.core.test_generator_project_enrichment` for project-level enrichment.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3.document import _magika_version, build
from pitloom.core.creation import CreationMetadata, Creator
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectFile, ProjectMetadata


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
    from importlib.metadata import PackageNotFoundError

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
