# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for metadata provenance tracking in SBOM generation."""

import json
import tempfile
from pathlib import Path

from pitloom.assemble import generate_project_sbom
from pitloom.core.creation import CreationMetadata, Creator
from pitloom.extract._pyproject import read_pyproject


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

        metadata, _ = read_pyproject(pyproject_path)

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

        metadata, _ = read_pyproject(pyproject_path)

        # Check that provenance tracks the dynamic version source
        assert "version" in metadata.provenance
        assert "src/mypackage/__about__.py" in metadata.provenance["version"]
        assert "dynamic_extraction" in metadata.provenance["version"]


def test_provenance_in_sbom_output() -> None:
    """In the default minimal mode, provenance appears for high-signal fields
    (e.g. the inferred copyright) but NOT for trivially-native ones (name,
    which is already ``Element.name`` read verbatim from pyproject.toml)."""
    pyproject_content = """
[project]
name = "test-pkg"
version = "1.0.0"
description = "A test package"
dependencies = ["requests>=2.28.0"]
authors = [{name = "Jane Doe"}]
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        sbom_json = generate_project_sbom(
            tmppath,
            creation_metadata=CreationMetadata(creators=[Creator(name="Test")]),
        )
        sbom_data = json.loads(sbom_json)

        main_package = next(
            elem
            for elem in sbom_data["@graph"]
            if elem["type"] == "software_Package" and elem["name"] == "test-pkg"
        )
        comment = main_package["comment"]

        # High-signal (inferred) copyright provenance is kept ...
        assert "Metadata provenance:" in comment
        assert "copyright_text:" in comment
        assert "inferred_from_authors" in comment
        # ... but the trivial name/version field-source is dropped in minimal.
        assert "project.name" not in comment


def test_provenance_in_dependency_packages() -> None:
    """Dependency packages keep the high-signal declared constraint (which has
    no native SPDX home), not the trivial 'dependencies came from pyproject'."""
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

        sbom_json = generate_project_sbom(tmppath)
        sbom_data = json.loads(sbom_json)

        dep_packages = [
            elem
            for elem in sbom_data["@graph"]
            if elem["type"] == "software_Package"
            and elem["name"] in ["numpy", "pandas"]
        ]
        assert len(dep_packages) == 2

        for dep_pkg in dep_packages:
            assert "comment" in dep_pkg
            assert "Metadata provenance:" in dep_pkg["comment"]
            assert "declared_constraint:" in dep_pkg["comment"]


def test_provenance_not_recorded_on_relationships() -> None:
    """Dependency ``dependsOn`` relationships carry no provenance Annotation or
    comment: the relationship is itself the native record, so annotating the
    edge would just shadow native SPDX."""
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

        sbom_json = generate_project_sbom(tmppath)
        graph = json.loads(sbom_json)["@graph"]

        relationships = [e for e in graph if e["type"] == "Relationship"]
        assert len(relationships) > 0
        for rel in relationships:
            assert "Metadata provenance" not in (rel.get("comment") or "")

        rel_ids = {r["spdxId"] for r in relationships}
        annotations = [e for e in graph if e["type"] == "Annotation"]
        assert not any(a.get("subject") in rel_ids for a in annotations)


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

        metadata, _ = read_pyproject(pyproject_path)

        # Check that provenance tracks authors
        assert "authors" in metadata.provenance
        assert "pyproject.toml" in metadata.provenance["authors"]

        # Check that copyright provenance is tracked
        assert "copyright_text" in metadata.provenance
        assert "inferred_from_authors" in metadata.provenance["copyright_text"]


def test_provenance_emitted_as_annotation_in_sbom_output() -> None:
    """The default provenance_format ("both") records high-signal provenance as
    a Core Annotation in addition to the legacy comment (see
    test_annotation_provenance_emit.py and the implementation design doc)."""
    pyproject_content = """
[project]
name = "test-pkg"
version = "1.0.0"
description = "A test package"
authors = [{name = "Jane Doe"}]
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        sbom_json = generate_project_sbom(tmppath)
        sbom_data = json.loads(sbom_json)
        graph = sbom_data["@graph"]

        main_package = next(
            elem
            for elem in graph
            if elem["type"] == "software_Package" and elem["name"] == "test-pkg"
        )

        annotations = [
            elem
            for elem in graph
            if elem["type"] == "Annotation"
            and elem.get("subject") == main_package["spdxId"]
        ]
        assert len(annotations) == 1
        assert annotations[0]["annotationType"] == "other"
        assert annotations[0]["contentType"] == "application/json"
        statement = json.loads(annotations[0]["statement"])
        # Only the high-signal (inferred) field is present in minimal mode.
        assert set(statement["fields"]) == {"copyright_text"}
        assert (
            statement["fields"]["copyright_text"]["method"] == "inferred_from_authors"
        )

        # "both" (the default) still writes the legacy comment too.
        assert "Metadata provenance:" in main_package["comment"]
