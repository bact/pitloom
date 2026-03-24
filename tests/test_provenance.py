# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for metadata provenance tracking in SBOM generation."""

import json
import tempfile
from pathlib import Path

from loom.extractors.metadata import extract_metadata_from_pyproject
from loom.generator import generate_sbom_from_project


def test_provenance_basic_fields() -> None:
    """Test that provenance is tracked for basic metadata fields."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"
description = "A test package"
dependencies = ["requests>=2.28.0"]

[project.urls]
Homepage = "https://example.com"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        metadata = extract_metadata_from_pyproject(pyproject_path)

        # Check that provenance is tracked
        assert "name" in metadata.provenance
        assert "pyproject.toml" in metadata.provenance["name"]
        assert "project.name" in metadata.provenance["name"]

        assert "version" in metadata.provenance
        assert "pyproject.toml" in metadata.provenance["version"]
        assert "project.version" in metadata.provenance["version"]

        assert "description" in metadata.provenance
        assert "pyproject.toml" in metadata.provenance["description"]

        assert "dependencies" in metadata.provenance
        assert "pyproject.toml" in metadata.provenance["dependencies"]

        assert "urls" in metadata.provenance
        assert "pyproject.toml" in metadata.provenance["urls"]


def test_provenance_dynamic_version() -> None:
    """Test that provenance tracks dynamic version extraction."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create project structure
        src_dir = tmppath / "src" / "mypackage"
        src_dir.mkdir(parents=True)

        # Create __about__.py with version
        about_py = src_dir / "__about__.py"
        about_py.write_text('__version__ = "2.3.4"')

        # Create pyproject.toml with dynamic version
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(
            """
[project]
name = "mypackage"
dynamic = ["version"]
description = "A test package"

[tool.hatch.version]
path = "src/mypackage/__about__.py"
"""
        )

        metadata = extract_metadata_from_pyproject(pyproject_path)

        # Check that provenance tracks the dynamic version source
        assert "version" in metadata.provenance
        assert "src/mypackage/__about__.py" in metadata.provenance["version"]
        assert "dynamic_extraction" in metadata.provenance["version"]


def test_provenance_in_sbom_output() -> None:
    """Test that provenance appears in the generated SBOM."""
    pyproject_content = """
[project]
name = "test-pkg"
version = "1.0.0"
description = "A test package"
dependencies = ["requests>=2.28.0"]
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        sbom_json = generate_sbom_from_project(tmppath, creator_name="Test")
        sbom_data = json.loads(sbom_json)

        # Find the main package
        packages = [
            elem
            for elem in sbom_data["@graph"]
            if elem["type"] == "software_Package" and elem["name"] == "test-pkg"
        ]
        assert len(packages) == 1

        main_package = packages[0]
        assert "comment" in main_package
        comment = main_package["comment"]

        # Check that provenance information is in the comment
        assert "Metadata provenance:" in comment
        assert "name:" in comment
        assert "pyproject.toml" in comment
        assert "project.name" in comment


def test_provenance_in_dependency_packages() -> None:
    """Test that provenance is tracked for dependency packages."""
    pyproject_content = """
[project]
name = "main-pkg"
version = "1.0.0"
dependencies = ["numpy==1.24.0", "pandas>=1.5.0"]
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        sbom_json = generate_sbom_from_project(tmppath)
        sbom_data = json.loads(sbom_json)

        # Find dependency packages
        dep_packages = [
            elem
            for elem in sbom_data["@graph"]
            if elem["type"] == "software_Package"
            and elem["name"] in ["numpy", "pandas"]
        ]
        assert len(dep_packages) == 2

        # Check that all dependency packages have provenance comments
        for dep_pkg in dep_packages:
            assert "comment" in dep_pkg
            assert "Metadata provenance:" in dep_pkg["comment"]
            assert "dependencies:" in dep_pkg["comment"]


def test_provenance_in_relationships() -> None:
    """Test that provenance is tracked in relationships."""
    pyproject_content = """
[project]
name = "main-pkg"
version = "1.0.0"
dependencies = ["requests>=2.28.0"]
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        sbom_json = generate_sbom_from_project(tmppath)
        sbom_data = json.loads(sbom_json)

        # Find relationships
        relationships = [
            elem for elem in sbom_data["@graph"] if elem["type"] == "Relationship"
        ]
        assert len(relationships) > 0

        # Check that relationships have provenance comments
        for rel in relationships:
            if rel["relationshipType"] == "dependsOn":
                assert "comment" in rel
                assert "Metadata provenance:" in rel["comment"]
                assert "dependencies:" in rel["comment"]


def test_provenance_with_authors() -> None:
    """Test that provenance tracks author information."""
    pyproject_content = """
[project]
name = "test-pkg"
version = "1.0.0"
authors = [
    {name = "John Doe", email = "john@example.com"}
]
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        metadata = extract_metadata_from_pyproject(pyproject_path)

        # Check that provenance tracks authors
        assert "authors" in metadata.provenance
        assert "pyproject.toml" in metadata.provenance["authors"]

        # Check that copyright provenance is tracked
        assert "copyright_text" in metadata.provenance
        assert "inferred_from_authors" in metadata.provenance["copyright_text"]
