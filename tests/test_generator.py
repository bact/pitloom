# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for SBOM generation."""

import json
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.__about__ import __version__
from pitloom.assemble import (
    enrich_model,
    generate,
    generate_env_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.assemble.spdx3.document import build, build_deployed, build_model
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata, Creator, Tool
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.document import DocumentModel
from pitloom.core.models import generate_spdx_id
from pitloom.core.project import PhantomDependency, ProjectFile, ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.extract.ai_model import read_ai_model
from pitloom.ids import IdRegistry


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


def test_build_package_files_have_sha256_verified_using() -> None:
    """Every file (not directory) software_File must carry a SHA-256
    verifiedUsing hash matching the corresponding ProjectFile.digest_sha256."""
    files = [
        ProjectFile(
            physical_path="src/pkg/__init__.py",
            distribution_path="pkg/__init__.py",
            digest_sha256="a" * 64,
        ),
        ProjectFile(
            physical_path="src/pkg/module.py",
            distribution_path="pkg/module.py",
            digest_sha256="b" * 64,
        ),
    ]
    project = ProjectMetadata(name="file-hash-project", version="1.0.0", files=files)
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    file_elements = [e for e in graph if e.get("type") == "software_File"]
    by_name = {e["name"]: e for e in file_elements}

    # Directory node: no verifiedUsing hash.
    assert "verifiedUsing" not in by_name["pkg"]

    # File nodes: exactly one SHA-256 Hash matching the source digest.
    for pf in files:
        file_elem = by_name[pf.distribution_path]
        assert file_elem["software_fileKind"] == "file"
        (hash_obj,) = file_elem["verifiedUsing"]
        assert hash_obj["algorithm"] == "sha256"
        assert hash_obj["hashValue"] == pf.digest_sha256


def _build_graph_for_files(files: list[ProjectFile]) -> list[dict[str, object]]:
    """Build a minimal document from *files* and return its ``@graph``."""
    project = ProjectMetadata(name="file-headers-project", version="1.0.0", files=files)
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())
    exporter = build(doc)
    graph: list[dict[str, object]] = json.loads(exporter.to_json())["@graph"]
    return graph


def _find_file_element(
    graph: list[dict[str, object]], distribution_path: str
) -> dict[str, object]:
    return next(
        e
        for e in graph
        if e.get("type") == "software_File" and e.get("name") == distribution_path
    )


def _annotation_fields_for(
    graph: list[dict[str, object]], subject_spdx_id: object
) -> dict[str, dict[str, str]] | None:
    """Return the decoded ``fields`` map of the ``provenance/fields/1``
    Annotation on *subject_spdx_id*, or ``None`` if there isn't one."""
    for element in graph:
        if element.get("type") != "Annotation":
            continue
        if element.get("subject") != subject_spdx_id:
            continue
        statement = json.loads(element["statement"])  # type: ignore[arg-type]
        if statement.get("kind") == "fields":
            return statement["fields"]  # type: ignore[no-any-return]
    return None


def test_build_file_native_copyright_and_declared_license() -> None:
    """A file's own SPDX-FileCopyrightText/License-Identifier tags set
    native fields directly; the license relationship is hasDeclaredLicense,
    never hasConcludedLicense (a file's own tag always is its own claim,
    nothing to classify against)."""
    files = [
        ProjectFile(
            physical_path="src/pkg/tagged.py",
            distribution_path="pkg/tagged.py",
            digest_sha256="a" * 64,
            copyright_text="2026 Test Author",
            copyright_source="spdx_tag",
            spdx_license_identifier="MIT",
        )
    ]
    graph = _build_graph_for_files(files)
    file_elem = _find_file_element(graph, "pkg/tagged.py")

    assert file_elem["software_copyrightText"] == "2026 Test Author"

    relationships = [e for e in graph if e.get("type") == "Relationship"]
    license_rels = [r for r in relationships if r.get("from") == file_elem["spdxId"]]
    assert [r["relationshipType"] for r in license_rels] == ["hasDeclaredLicense"]

    license_targets = license_rels[0]["to"]
    assert isinstance(license_targets, list)
    license_target_id = license_targets[0]
    license_elem = next(
        e
        for e in graph
        if e.get("type") == "simplelicensing_SimpleLicensingText"
        and e.get("spdxId") == license_target_id
    )
    assert license_elem["simplelicensing_licenseText"] == "MIT"


def test_build_file_primary_purpose_and_content_type_independent() -> None:
    """The README.md case: SPDX-FileType: DOCUMENTATION maps to
    primaryPurpose, and an independently-resolved content_type sets
    contentType -- both native, both set, neither gated on the other."""
    files = [
        ProjectFile(
            physical_path="README.md",
            distribution_path="README.md",
            digest_sha256="a" * 64,
            file_type="DOCUMENTATION",
            content_type="text/markdown",
            content_type_method="mimetype_extension_guess",
        )
    ]
    graph = _build_graph_for_files(files)
    file_elem = _find_file_element(graph, "README.md")

    assert file_elem["software_primaryPurpose"] == "documentation"
    assert file_elem["contentType"] == "text/markdown"
    assert "summary" not in file_elem

    fields = _annotation_fields_for(graph, file_elem["spdxId"])
    assert fields is not None
    # declared: no Method segment recorded.
    assert "method" not in fields["file_type"]
    # detected: Method segment present, distinct field key from file_type.
    assert fields["content_type"]["method"] == "mimetype_extension_guess"


def test_build_file_unmapped_file_type_goes_to_summary_not_content_type() -> None:
    """An unmapped SPDX-FileType (no SoftwarePurpose equivalent) with no
    content_type resolved: the raw tag value lands in File.summary, no
    primaryPurpose or contentType is set, no error."""
    files = [
        ProjectFile(
            physical_path="logo.png",
            distribution_path="logo.png",
            digest_sha256="a" * 64,
            file_type="IMAGE",
        )
    ]
    graph = _build_graph_for_files(files)
    file_elem = _find_file_element(graph, "logo.png")

    assert "software_primaryPurpose" not in file_elem
    assert "contentType" not in file_elem
    assert file_elem["summary"] == "FileType: IMAGE"

    # An unmapped file_type still gets a provenance entry recording where
    # the raw value came from, same as the mapped case -- summary-only
    # placement isn't a reason to drop provenance.
    fields = _annotation_fields_for(graph, file_elem["spdxId"])
    assert fields is not None
    assert fields["file_type"]["source"] == "logo.png"
    assert fields["file_type"]["location"] == "SPDX-FileType"


def test_build_file_primary_purpose_never_inferred_from_content_type() -> None:
    """Regression guard: a resolved content_type must never backfill
    primaryPurpose, even when file_type is absent entirely -- SoftwarePurpose
    is about usage, not content, per the SPDX 3 spec."""
    files = [
        ProjectFile(
            physical_path="photo.jpg",
            distribution_path="photo.jpg",
            digest_sha256="a" * 64,
            content_type="image/jpeg",
            content_type_method="magika",
        )
    ]
    graph = _build_graph_for_files(files)
    file_elem = _find_file_element(graph, "photo.jpg")

    assert file_elem["contentType"] == "image/jpeg"
    assert "software_primaryPurpose" not in file_elem
    assert "summary" not in file_elem  # no file_type tag at all -- nothing to record


def test_build_file_contributors_only_in_summary_never_native() -> None:
    """FileContributor values appear only in File.summary, sorted, never
    natively -- the Annotation carries a plain source-tracking entry with
    no value duplicated into it."""
    files = [
        ProjectFile(
            physical_path="pkg/mod.py",
            distribution_path="pkg/mod.py",
            digest_sha256="a" * 64,
            file_contributors=["Bob", "Alice"],
        )
    ]
    graph = _build_graph_for_files(files)
    file_elem = _find_file_element(graph, "pkg/mod.py")

    assert file_elem["summary"] == "Contributor: Alice; Contributor: Bob"

    fields = _annotation_fields_for(graph, file_elem["spdxId"])
    assert fields is not None
    assert "Alice" not in fields["file_contributors"]["source"]
    assert "Bob" not in fields["file_contributors"]["source"]


def test_build_file_summary_combines_contributors_and_file_type_sorted() -> None:
    """A file with both contributors and an unmapped file_type produces one
    combined summary string, sorted by key then value ('Contributor'
    entries before 'FileType', per the alphabetical-by-key rule)."""
    files = [
        ProjectFile(
            physical_path="pkg/mixed.bin",
            distribution_path="pkg/mixed.bin",
            digest_sha256="a" * 64,
            file_contributors=["Zoe", "Amy"],
            file_type="BINARY",
        )
    ]
    graph = _build_graph_for_files(files)
    file_elem = _find_file_element(graph, "pkg/mixed.bin")

    assert file_elem["summary"] == (
        "Contributor: Amy; Contributor: Zoe; FileType: BINARY"
    )


def test_build_file_no_header_data_emits_nothing_extra() -> None:
    """A file with no header-derived data at all gets no summary, no
    Annotation, no license relationship, and no native copyright/purpose/
    contentType fields -- matches today's pre-feature output exactly."""
    files = [
        ProjectFile(
            physical_path="pkg/plain.py",
            distribution_path="pkg/plain.py",
            digest_sha256="a" * 64,
        )
    ]
    graph = _build_graph_for_files(files)
    file_elem = _find_file_element(graph, "pkg/plain.py")

    assert "summary" not in file_elem
    assert "software_copyrightText" not in file_elem
    assert "software_primaryPurpose" not in file_elem
    assert "contentType" not in file_elem
    assert _annotation_fields_for(graph, file_elem["spdxId"]) is None
    relationships = [e for e in graph if e.get("type") == "Relationship"]
    assert not [r for r in relationships if r.get("from") == file_elem["spdxId"]]


def test_build_file_shared_license_dedupes_to_one_element() -> None:
    """Two files declaring the same SPDX-License-Identifier reuse one
    SimpleLicensingText element, with two separate relationships."""
    files = [
        ProjectFile(
            physical_path="pkg/a.py",
            distribution_path="pkg/a.py",
            digest_sha256="a" * 64,
            spdx_license_identifier="Apache-2.0",
        ),
        ProjectFile(
            physical_path="pkg/b.py",
            distribution_path="pkg/b.py",
            digest_sha256="b" * 64,
            spdx_license_identifier="Apache-2.0",
        ),
    ]
    graph = _build_graph_for_files(files)

    license_elements = [
        e
        for e in graph
        if e.get("type") == "simplelicensing_SimpleLicensingText"
        and e.get("simplelicensing_licenseText") == "Apache-2.0"
    ]
    assert len(license_elements) == 1

    license_spdx_id = license_elements[0]["spdxId"]
    declared_rels = [
        e
        for e in graph
        if e.get("type") == "Relationship"
        and e.get("relationshipType") == "hasDeclaredLicense"
        and e.get("to") == [license_spdx_id]
    ]
    assert len(declared_rels) == 2


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


def test_generate_project_sbom_creation_comment_and_no_tool() -> None:
    """Creation comment must map to CreationInfo.comment and tool is optional."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "comment-app"
version = "0.1.0"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        sbom_json = generate_project_sbom(
            tmppath,
            creation_metadata=CreationMetadata(
                creators=[Creator(name="Test Creator")],
                tools=[],
                creation_comment="Generated in CI",
            ),
        )
        sbom_data = json.loads(sbom_json)
        graph = sbom_data["@graph"]

        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        assert creation_infos[0]["comment"] == "Generated in CI"
        assert "createdUsing" not in creation_infos[0]

        tool_elements = [e for e in graph if e["type"] == "Tool"]
        assert not tool_elements


def test_generate_project_sbom_tool_summary_default_and_no_comment() -> None:
    """Default creation_tool gets a Pitloom-versioned summary; no comment by default."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "summary-app"
version = "0.1.0"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        sbom_json = generate_project_sbom(tmppath)
        sbom_data = json.loads(sbom_json)
        graph = sbom_data["@graph"]

        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        assert "comment" not in creation_infos[0]

        tool_elements = [e for e in graph if e["type"] == "Tool"]
        assert len(tool_elements) == 1
        assert tool_elements[0]["name"] == "Pitloom"
        assert tool_elements[0]["summary"] == f"Pitloom {__version__}"


def test_generate_project_sbom_tool_summary_omitted_for_custom_tool_name() -> None:
    """A user-supplied tool name gets no Pitloom-version summary."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "custom-tool-app"
version = "0.1.0"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        sbom_json = generate_project_sbom(
            tmppath,
            creation_metadata=CreationMetadata(tools=[Tool("MyWrapper")]),
        )
        sbom_data = json.loads(sbom_json)
        graph = sbom_data["@graph"]

        tool_elements = [e for e in graph if e["type"] == "Tool"]
        assert len(tool_elements) == 1
        assert tool_elements[0]["name"] == "MyWrapper"
        assert "summary" not in tool_elements[0]


def _creation_agents(graph: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the elements referenced by the single CreationInfo.createdBy."""
    creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
    assert len(creation_infos) == 1
    by_id = {e["spdxId"]: e for e in graph if "spdxId" in e}
    return [by_id[ref] for ref in creation_infos[0]["createdBy"]]


def test_generate_project_sbom_default_creator_is_software_agent() -> None:
    """With no named creator, createdBy is the SoftwareAgent "Pitloom", not a
    Person, and the package asserts no suppliedBy."""
    pyproject_content = """
[project]
name = "anon-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        graph = json.loads(generate_project_sbom(tmppath))["@graph"]

        agents = _creation_agents(graph)
        assert [a["type"] for a in agents] == ["SoftwareAgent"]
        assert agents[0]["name"] == "Pitloom"
        assert not [e for e in graph if e["type"] == "Person"]

        packages = [e for e in graph if e["type"] == "software_Package"]
        assert packages and all("suppliedBy" not in p for p in packages)


def test_generate_project_sbom_named_creator_is_person_with_supplied_by() -> None:
    """A named creator becomes a Person in createdBy and the main package's
    suppliedBy."""
    pyproject_content = """
[project]
name = "named-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        graph = json.loads(
            generate_project_sbom(
                tmppath,
                creation_metadata=CreationMetadata(
                    creators=[Creator(name="Alice", email="alice@example.com")]
                ),
            )
        )["@graph"]

        agents = _creation_agents(graph)
        assert [a["type"] for a in agents] == ["Person"]
        assert agents[0]["name"] == "Alice"

        main_pkg = next(
            e
            for e in graph
            if e["type"] == "software_Package" and e["name"] == "named-app"
        )
        assert main_pkg["suppliedBy"] == agents[0]["spdxId"]


def test_generate_project_sbom_organization_creator() -> None:
    """type='organization' makes the named creator an Organization."""
    pyproject_content = """
[project]
name = "org-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        graph = json.loads(
            generate_project_sbom(
                tmppath,
                creation_metadata=CreationMetadata(
                    creators=[Creator(name="Acme Corp", type="organization")]
                ),
            )
        )["@graph"]

        agents = _creation_agents(graph)
        assert [a["type"] for a in agents] == ["Organization"]
        assert agents[0]["name"] == "Acme Corp"


@pytest.mark.parametrize(
    ("creator_type", "expected_element_type"),
    [
        ("person", "Person"),
        ("organization", "Organization"),
        ("software-agent", "SoftwareAgent"),
        ("agent", "Agent"),
    ],
)
def test_generate_project_sbom_all_valid_creator_types(
    creator_type: str, expected_element_type: str
) -> None:
    """Every SPDX 3 Agent subclass is a valid createdBy type: Person,
    Organization, SoftwareAgent, and the generic Agent."""
    pyproject_content = """
[project]
name = "creator-type-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        graph = json.loads(
            generate_project_sbom(
                tmppath,
                creation_metadata=CreationMetadata(
                    creators=[Creator(name="Bot", type=creator_type)]
                ),
            )
        )["@graph"]

        agents = _creation_agents(graph)
        assert [a["type"] for a in agents] == [expected_element_type]
        assert agents[0]["name"] == "Bot"


def test_generate_project_sbom_invalid_creator_type_raises() -> None:
    """An unrecognised creator type raises ValueError naming the valid set,
    rather than silently falling back to Person."""
    pyproject_content = """
[project]
name = "bad-creator-type-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        with pytest.raises(ValueError, match="Invalid creator type"):
            generate_project_sbom(
                tmppath,
                creation_metadata=CreationMetadata(
                    creators=[Creator(name="Bot", type="robot")]
                ),
            )


def test_generate_project_sbom_creation_datetime_normalized_on_export() -> None:
    """Full ISO creation_datetime must be normalised only at SPDX export time."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "datetime-app"
version = "0.1.0"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        sbom_json = generate_project_sbom(
            tmppath,
            creation_metadata=CreationMetadata(
                creators=[Creator(name="Test Creator")],
                creation_datetime="2026-01-01T12:34:56.789123+02:30",
            ),
        )
        sbom_data = json.loads(sbom_json)
        graph = sbom_data["@graph"]

        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        assert creation_infos[0]["created"] == "2026-01-01T10:04:56Z"


def test_generate_project_sbom_multiple_creators_and_supplied_by_first() -> None:
    """Multiple creators each become their own Agent in createdBy, of the
    correct subclass; suppliedBy on the main package is the *first* named
    creator."""
    pyproject_content = """
[project]
name = "multi-creator-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        graph = json.loads(
            generate_project_sbom(
                tmppath,
                creation_metadata=CreationMetadata(
                    creators=[
                        Creator(name="Acme Corp", type="organization"),
                        Creator(name="Alice", email="alice@example.com"),
                    ]
                ),
            )
        )["@graph"]

        agents = _creation_agents(graph)
        assert [a["type"] for a in agents] == ["Organization", "Person"]
        assert agents[0]["name"] == "Acme Corp"
        assert agents[1]["name"] == "Alice"

        main_pkg = next(
            e
            for e in graph
            if e["type"] == "software_Package" and e["name"] == "multi-creator-app"
        )
        assert main_pkg["suppliedBy"] == agents[0]["spdxId"]


def test_generate_project_sbom_multiple_creators_same_type_distinct_agents() -> None:
    """Two creators of the *same* type each become their own Agent, with
    distinct spdxIds, and both are present in createdBy -- same-type
    creators must not collapse into a single Agent."""
    pyproject_content = """
[project]
name = "multi-person-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        graph = json.loads(
            generate_project_sbom(
                tmppath,
                creation_metadata=CreationMetadata(
                    creators=[
                        Creator(name="Alice", type="person"),
                        Creator(name="Bob", type="person"),
                    ]
                ),
            )
        )["@graph"]

        agents = _creation_agents(graph)
        assert [a["type"] for a in agents] == ["Person", "Person"]
        assert [a["name"] for a in agents] == ["Alice", "Bob"]
        assert agents[0]["spdxId"] != agents[1]["spdxId"]

        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        assert set(creation_infos[0]["createdBy"]) == {
            agents[0]["spdxId"],
            agents[1]["spdxId"],
        }


def test_generate_project_sbom_multiple_tools() -> None:
    """Multiple tools each become their own Tool in createdUsing."""
    pyproject_content = """
[project]
name = "multi-tool-app"
version = "0.1.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        sbom_json = generate_project_sbom(
            tmppath,
            creation_metadata=CreationMetadata(
                tools=[Tool("Pitloom"), Tool("MyWrapper")]
            ),
        )
        graph = json.loads(sbom_json)["@graph"]

        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        by_id = {e["spdxId"]: e for e in graph if "spdxId" in e}
        tools = [by_id[ref] for ref in creation_infos[0]["createdUsing"]]

        assert [t["name"] for t in tools] == ["Pitloom", "MyWrapper"]
        assert tools[0]["summary"] == f"Pitloom {__version__}"
        assert "summary" not in tools[1]


def test_generate_project_sbom_sentimentdemo_structure() -> None:
    """Test SBOM generation with sentimentdemo-like structure."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "sentimentdemo"
dynamic = ["version"]
description = "A simple sentiment analysis application"
readme = "README.md"
requires-python = ">=3.10"
license = "CC0-1.0"
keywords = ["sbom", "spdx", "ai", "nlp"]
authors = [{ name = "Test Author", email = "test@example.com" }]
dependencies = [
    "fasttext==0.9.3",
    "newmm-tokenizer==0.2.2",
    "numpy==1.26.4",
]

[project.urls]
Source = "https://github.com/bact/sentimentdemo"
"""

    about_content = '__version__ = "0.1.0"'

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        # Create version file
        src_dir = tmppath / "src" / "sentimentdemo"
        src_dir.mkdir(parents=True)
        about_path = src_dir / "__about__.py"
        about_path.write_text(about_content)

        sbom_json = generate_project_sbom(tmppath)
        sbom_data = json.loads(sbom_json)

        # Verify structure
        graph = sbom_data["@graph"]
        packages = [elem for elem in graph if elem["type"] == "software_Package"]

        # Check main package
        main_package = [p for p in packages if p["name"] == "sentimentdemo"][0]
        assert main_package["software_packageVersion"] == "0.1.0"

        # Check dependencies
        dep_names = {p["name"] for p in packages if p["name"] != "sentimentdemo"}
        assert "fasttext" in dep_names
        assert "newmm-tokenizer" in dep_names
        assert "numpy" in dep_names

        # Check relationships
        relationships = [elem for elem in graph if elem["type"] == "Relationship"]
        assert len(relationships) >= 3  # At least 3 dependencies


def test_generate_project_sbom_dependency_names_with_markers_and_specifiers() -> None:
    """Dependency names must be clean even with markers and multi-clause specifiers.

    Regression guard: a naive operator-substring split on a fixed priority
    order (``===``, ``~=``, ``!=``, ``==``, ``>=``, ``<=``, ``>``, ``<``)
    mis-parses two real-world shapes -- an environment marker's own ``==``
    comparison being matched before the specifier's real operator (e.g.
    ``pkg>=1.0; sys_platform == 'linux'``), and a later clause's operator
    appearing earlier in the string than an earlier clause's (e.g.
    ``pkg>=0.1,<1``, which -- after ``packaging.Requirement`` reorders
    clauses -- puts ``<1`` before ``>=0.1``). Both previously produced a
    garbled package name (with leftover operators/markers) and no PURL.
    """
    pyproject_content = """
[project]
name = "markerdemo"
version = "0.1.0"
description = "Dependency-parsing regression fixture"
dependencies = [
    "auditwheel>=6.7.0; sys_platform == 'linux'",
    "py-spdx-license>=0.0.1,<1",
    "pyyaml>=6.0.3,<7",
]
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        sbom_json = generate_project_sbom(tmppath)
        sbom_data = json.loads(sbom_json)

        graph = sbom_data["@graph"]
        packages = {
            p["name"]: p
            for p in graph
            if p["type"] == "software_Package" and p["name"] != "markerdemo"
        }

        assert set(packages) == {"auditwheel", "py-spdx-license", "pyyaml"}
        for name, pkg in packages.items():
            assert ";" not in name
            assert not any(op in name for op in (">=", "<=", "==", "<", ">"))
            version = pkg.get("software_packageVersion")
            assert version is not None
            assert ";" not in version and "'" not in version
            # Every dependency gets a PURL, even with an unresolved version
            # (e.g. an unpinned, platform-gated requirement not installed
            # in the current environment) -- name-only is still a valid,
            # matchable purl-spec identifier, preferable to none at all.
            purl = pkg["software_packageUrl"]
            expected = f"pkg:pypi/{name}" + (
                "" if version == "unknown" else f"@{version}"
            )
            assert purl == expected


def test_build_main_package_noassertion_license_when_undeclared() -> None:
    """The main project package must assert ``hasDeclaredLicense:
    NOASSERTION`` when no license is declared anywhere, rather than
    silently having no license relationship at all -- same policy as
    dependency packages (see add_dependencies)."""
    project = ProjectMetadata(name="nolicenseproject", version="1.0.0")
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    exporter = build(doc)
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    main_pkg = next(
        p
        for p in graph
        if p.get("type") == "software_Package" and p["name"] == "nolicenseproject"
    )
    licenses = [
        e for e in graph if e.get("type") == "simplelicensing_SimpleLicensingText"
    ]
    noassertion = next(
        lic
        for lic in licenses
        if lic.get("simplelicensing_licenseText") == "NOASSERTION"
    )

    rels = [e for e in graph if e.get("type") == "Relationship"]
    license_rels = [
        r
        for r in rels
        if r.get("from") == main_pkg["spdxId"]
        and r.get("relationshipType") == "hasDeclaredLicense"
    ]
    assert len(license_rels) == 1
    assert license_rels[0]["to"] == [noassertion["spdxId"]]

    spdx_docs = [e for e in graph if e.get("type") == "SpdxDocument"]
    assert "simpleLicensing" in spdx_docs[0]["profileConformance"]


def test_generate_project_sbom_with_fragments() -> None:
    """Test SBOM generation with external generic SBOM fragments."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "fragment-app"
version = "1.0.0"
description = "App with fragments"

[tool.pitloom.fragments]
files = ["fragment1.json", "fragment2.json"]
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        # Create dummy fragment 1 with an AI Package
        doc_uuid_1 = "aaaa-bbbb"
        ci1 = spdx3.CreationInfo(
            specVersion="3.0.1", created=datetime.now(timezone.utc)
        )
        person1 = spdx3.Person(
            spdxId=generate_spdx_id("Person", "author1", doc_uuid_1),
            name="Author 1",
            creationInfo=ci1,
        )
        ci1.createdBy = [require_spdx_id(person1)]
        ai_pkg = spdx3.ai_AIPackage(
            spdxId=generate_spdx_id("AIPackage", "test-ai-model", doc_uuid_1),
            name="cool-ai-model",
            creationInfo=ci1,
        )
        exporter1 = Spdx3JsonExporter()
        exporter1.add_person(person1)
        exporter1.add_package(ai_pkg)
        (tmppath / "fragment1.json").write_text(exporter1.to_json())

        # Create dummy fragment 2 with a Dataset Package
        doc_uuid_2 = "cccc-dddd"
        ci2 = spdx3.CreationInfo(
            specVersion="3.0.1", created=datetime.now(timezone.utc)
        )
        person2 = spdx3.Person(
            spdxId=generate_spdx_id("Person", "author2", doc_uuid_2),
            name="Author 2",
            creationInfo=ci2,
        )
        ci2.createdBy = [require_spdx_id(person2)]
        dataset_pkg = spdx3.dataset_DatasetPackage(
            spdxId=generate_spdx_id("DatasetPackage", "test-dataset", doc_uuid_2),
            name="cool-dataset",
            creationInfo=ci2,
        )
        dataset_pkg.dataset_datasetType = [spdx3.dataset_DatasetType.text]
        exporter2 = Spdx3JsonExporter()
        exporter2.add_person(person2)
        exporter2.add_package(dataset_pkg)
        (tmppath / "fragment2.json").write_text(exporter2.to_json())

        sbom_json = generate_project_sbom(tmppath)
        sbom_data = json.loads(sbom_json)

        # Validate that elements from fragments are included in the graph
        graph = sbom_data["@graph"]
        element_types = {elem["type"] for elem in graph}

        assert "ai_AIPackage" in element_types
        assert "dataset_DatasetPackage" in element_types
        assert "software_Package" in element_types

        # Verify names
        ai_packages = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert ai_packages[0]["name"] == "cool-ai-model"

        dataset_packages = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert dataset_packages[0]["name"] == "cool-dataset"


def test_generate_project_sbom_setup_cfg_only_project() -> None:
    """generate_project_sbom() must support projects with no pyproject.toml at all,
    falling back to setup.cfg via the shared read_project() helper.

    Regression test: generate_project_sbom() previously hardcoded a pyproject.toml
    read with no setup.cfg/setup.py fallback, so a setup.cfg-only project
    raised FileNotFoundError.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "setup.cfg").write_text(
            "[metadata]\nname = setup-cfg-only-package\nversion = 1.2.3\n"
        )

        sbom_json = generate_project_sbom(tmppath)
        graph = json.loads(sbom_json)["@graph"]

        packages = [e for e in graph if e.get("type") == "software_Package"]
        main_package = next(
            p for p in packages if p["name"] == "setup-cfg-only-package"
        )
        assert main_package["software_packageVersion"] == "1.2.3"


def test_generate_project_sbom_uses_preparsed_metadata_without_reparsing() -> None:
    """When metadata/pitloom_config are given, generate_project_sbom() must not
    re-parse project_dir via read_project()."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        # No pyproject.toml, setup.cfg, or setup.py -- read_project() would
        # raise FileNotFoundError if generate_project_sbom() called it.
        metadata = ProjectMetadata(name="preparsed-package", version="9.9.9")
        pitloom_config = PitloomConfig()

        sbom_json = generate_project_sbom(
            tmppath, project_metadata=metadata, pitloom_config=pitloom_config
        )
        graph = json.loads(sbom_json)["@graph"]

        packages = [e for e in graph if e.get("type") == "software_Package"]
        main_package = next(p for p in packages if p["name"] == "preparsed-package")
        assert main_package["software_packageVersion"] == "9.9.9"


def test_generate_project_sbom_partial_preparsed_args_reparses_both() -> None:
    """project_metadata and pitloom_config must be given together.

    Passing only one is treated as if neither were given: both are read
    fresh from project_dir, and the one caller-supplied value is ignored."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(
            '[project]\nname = "real-package"\nversion = "1.0.0"\n'
        )
        fake_metadata = ProjectMetadata(name="should-be-discarded")

        sbom_json = generate_project_sbom(
            tmppath, project_metadata=fake_metadata, pitloom_config=None
        )
        graph = json.loads(sbom_json)["@graph"]

        packages = [e for e in graph if e.get("type") == "software_Package"]
        names = [p["name"] for p in packages]
        assert "real-package" in names
        assert "should-be-discarded" not in names


def test_assembler_ai_model_with_inputs_outputs() -> None:
    """Test that AI model metadata with inputs/outputs is serialized into SPDX 3."""
    project = ProjectMetadata(name="ai-project", version="0.1.0")
    ai_model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.PYTORCH_PT2),
        name="linear-model",
        version="1.0.0",
        type_of_model="linear regression",
        inputs=[{"name": "x"}],
        outputs=[{"name": "linear"}],
        hyperparameters={"trainable": True},
        provenance={"inputs": "Source: model.pt2 | Field: models/model.json"},
    )
    doc = DocumentModel(
        project=project, creation_metadata=CreationMetadata(), ai_models=[ai_model]
    )

    exporter = build(doc)
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    pkg = ai_pkgs[0]
    assert pkg["name"] == "linear-model"
    assert pkg["software_packageVersion"] == "1.0.0"
    assert pkg["ai_typeOfModel"] == ["linear regression"]

    info = json.loads(pkg["ai_informationAboutApplication"])
    assert info["inputs"] == [{"name": "x"}]
    assert info["outputs"] == [{"name": "linear"}]

    hp = pkg["ai_hyperparameter"]
    assert any(e["key"] == "trainable" and e["value"] == "True" for e in hp)

    # profileConformance must include "ai"
    spdx_docs = [e for e in graph if e.get("type") == "SpdxDocument"]
    assert "ai" in spdx_docs[0]["profileConformance"]

    # contains relationship from main package to AI package
    rels = [e for e in graph if e.get("type") == "Relationship"]
    contains_rels = [r for r in rels if r.get("relationshipType") == "contains"]
    assert len(contains_rels) == 1
    assert any(pkg["spdxId"] in r["to"] for r in contains_rels)

    # no license relationship *from the AI package* when ai_model.license is
    # not set (the main project package gets its own NOASSERTION fallback
    # when it has no declared license either -- see build()'s license block
    # -- which is a separate, expected relationship, not this one).
    ai_pkg_license_rels = [
        r
        for r in rels
        if r.get("relationshipType") in ("hasDeclaredLicense", "hasConcludedLicense")
        and r.get("from") == pkg["spdxId"]
    ]
    assert not ai_pkg_license_rels


def test_assembler_usage_file_hasdatafile_is_lifecycle_scoped_runtime() -> None:
    """The ``hasDataFile`` relationship from a usage file (e.g. predict.py,
    which loads the model at inference time) to the model file must be a
    ``LifecycleScopedRelationship`` with ``scope: runtime`` -- contrast with
    ``pitloom.loom``'s ``generates`` edges, which are scoped ``build``."""
    project = ProjectMetadata(
        name="ai-project",
        version="0.1.0",
        files=[
            ProjectFile(
                physical_path="src/pkg/model.bin",
                distribution_path="pkg/model.bin",
                digest_sha256="a" * 64,
            ),
            ProjectFile(
                physical_path="src/pkg/predict.py",
                distribution_path="pkg/predict.py",
                digest_sha256="b" * 64,
            ),
        ],
    )
    ai_model = AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name="model.bin",
            file_path_relative="pkg/model.bin",
            model_format=AiModelFormat.PYTORCH_PT2,
        ),
        name="usage-model",
        usage_files=["pkg/predict.py"],
    )
    doc = DocumentModel(
        project=project, creation_metadata=CreationMetadata(), ai_models=[ai_model]
    )

    exporter = build(doc)
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    has_data_file = [
        e
        for e in graph
        if e.get("type") == "LifecycleScopedRelationship"
        and e.get("relationshipType") == "hasDataFile"
    ]
    assert len(has_data_file) == 1
    assert has_data_file[0]["scope"] == "runtime"

    # Plain "Relationship"-typed elements must not include a hasDataFile
    # edge -- it was reclassified, not duplicated.
    assert not any(
        e.get("type") == "Relationship" and e.get("relationshipType") == "hasDataFile"
        for e in graph
    )


def test_assembler_ai_model_reuses_registry_entity_by_physical_path() -> None:
    """A scan-discovered AI model must reuse a registry entity's spdxId when
    its physical path (project-root-relative, e.g. "src/pkg/model.bin") is
    registered -- the same string a pitloom.loom fragment's
    run.set_model(model_file_path, ...) call would have used, so the two
    become the same element once merged instead of yielding a second,
    duplicate ai_AIPackage."""
    project = ProjectMetadata(name="ai-project", version="0.1.0")
    ai_model = AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name="model.bin",
            physical_path="src/sentimentdemo/model.bin",
            model_format=AiModelFormat.FASTTEXT,
        ),
    )
    doc = DocumentModel(
        project=project, creation_metadata=CreationMetadata(), ai_models=[ai_model]
    )

    registry = IdRegistry.new("ai-project")
    registered_id = registry.register_entity(
        "src/sentimentdemo/model.bin", "ai_AIPackage"
    )

    exporter = build(doc, registry=registry)
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    assert ai_pkgs[0]["spdxId"] == registered_id


def test_assembler_ai_model_reuses_registry_entity_by_file_stem() -> None:
    """Falls back to the model file's stem (mirroring the lookup
    generate_model_sbom performs for loom model/--registry) when no
    physical_path or name match is registered."""
    project = ProjectMetadata(name="ai-project", version="0.1.0")
    ai_model = AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name="model.bin",
            model_format=AiModelFormat.FASTTEXT,
        ),
    )
    doc = DocumentModel(
        project=project, creation_metadata=CreationMetadata(), ai_models=[ai_model]
    )

    registry = IdRegistry.new("ai-project")
    registered_id = registry.register_entity("model", "ai_AIPackage")

    exporter = build(doc, registry=registry)
    graph = json.loads(exporter.to_json())["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    assert ai_pkgs[0]["spdxId"] == registered_id


def test_assembler_ai_model_no_registry_match_mints_fresh_id() -> None:
    """No matching registry entity -> unchanged behaviour: a fresh id is
    minted, and it does not collide with an unrelated registered entity."""
    project = ProjectMetadata(name="ai-project", version="0.1.0")
    ai_model = AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name="model.bin",
            physical_path="src/sentimentdemo/model.bin",
            model_format=AiModelFormat.FASTTEXT,
        ),
    )
    doc = DocumentModel(
        project=project, creation_metadata=CreationMetadata(), ai_models=[ai_model]
    )

    registry = IdRegistry.new("ai-project")
    unrelated_id = registry.register_entity("some-other-model", "ai_AIPackage")

    exporter = build(doc, registry=registry)
    graph = json.loads(exporter.to_json())["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    assert ai_pkgs[0]["spdxId"] != unrelated_id


def test_build_deployed_reuses_registry_entity_by_name() -> None:
    """A Deployed SBOM's installed packages must reuse a registered
    ``software_Package`` entity's spdxId (looked up by package name), so
    the same package referenced elsewhere (e.g. a Source or Analyzed SBOM)
    unifies with it once merged, instead of always minting a fresh id."""
    project = ProjectMetadata(name="deployed-environment", version="0.0.0")
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())
    env_tree = [
        {
            "package": {
                "key": "requests",
                "package_name": "requests",
                "installed_version": "2.31.0",
            }
        }
    ]

    registry = IdRegistry.new("deployed-environment")
    registered_id = registry.register_entity("requests", "software_Package")

    exporter = build_deployed(doc, env_tree, registry=registry)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = [e for e in graph if e.get("type") == "software_Package"]
    requests_pkg = next(p for p in packages if p["name"] == "requests")
    assert requests_pkg["spdxId"] == registered_id


def test_build_deployed_no_registry_match_mints_fresh_id() -> None:
    """No matching registry entity -> unchanged behaviour: a fresh id is
    minted for the installed package."""
    project = ProjectMetadata(name="deployed-environment", version="0.0.0")
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())
    env_tree = [
        {
            "package": {
                "key": "requests",
                "package_name": "requests",
                "installed_version": "2.31.0",
            }
        }
    ]

    registry = IdRegistry.new("deployed-environment")
    unrelated_id = registry.register_entity("some-other-package", "software_Package")

    exporter = build_deployed(doc, env_tree, registry=registry)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = [e for e in graph if e.get("type") == "software_Package"]
    requests_pkg = next(p for p in packages if p["name"] == "requests")
    assert requests_pkg["spdxId"] != unrelated_id


# ---------------------------------------------------------------------------
# Phantom dependency tests (add_phantom_dependencies via build())
# ---------------------------------------------------------------------------


def test_phantom_dependency_creates_package_and_dependency_relationship() -> None:
    """A phantom dependency produces a software_Package (name/version) and a
    dependsOn Relationship from the main package to it."""
    project = ProjectMetadata(name="main-project", version="1.0.0")
    doc = DocumentModel(
        project=project,
        creation_metadata=CreationMetadata(),
        phantom_dependencies=[
            PhantomDependency(
                name="libfoo",
                file_path="pkg.libs/libfoo.so",
                digest_sha256="c" * 64,
                version="1.2.3",
            )
        ],
    )

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = [e for e in graph if e.get("type") == "software_Package"]
    phantom_pkg = next(p for p in packages if p["name"] == "libfoo")
    assert phantom_pkg["software_packageVersion"] == "1.2.3"

    main_package = next(p for p in packages if p["name"] == "main-project")
    relationships = [e for e in graph if e.get("type") == "Relationship"]
    depends_on = [
        r
        for r in relationships
        if r["relationshipType"] == "dependsOn"
        and r["from"] == main_package["spdxId"]
        and phantom_pkg["spdxId"] in r["to"]
    ]
    assert len(depends_on) == 1

    # Same completeness policy as regular dependencies (add_dependencies):
    # NOASSERTION for copyright/license rather than a silently absent
    # field, and the bundled binary's own hash -- already computed
    # locally -- as its integrity hash.
    assert phantom_pkg["software_copyrightText"] == "NOASSERTION"
    assert phantom_pkg["verifiedUsing"] == [
        {"type": "Hash", "algorithm": "sha256", "hashValue": "c" * 64}
    ]
    license_rels = [
        r
        for r in relationships
        if r["relationshipType"] == "hasDeclaredLicense"
        and r["from"] == phantom_pkg["spdxId"]
    ]
    assert len(license_rels) == 1
    licenses = {
        e["spdxId"]: e
        for e in graph
        if e.get("type") == "simplelicensing_SimpleLicensingText"
    }
    assert (
        licenses[license_rels[0]["to"][0]]["simplelicensing_licenseText"]
        == "NOASSERTION"
    )


def test_phantom_dependency_without_version_is_unknown() -> None:
    """A phantom dependency with no inferred version gets 'unknown'."""
    project = ProjectMetadata(name="main-project", version="1.0.0")
    doc = DocumentModel(
        project=project,
        creation_metadata=CreationMetadata(),
        phantom_dependencies=[
            PhantomDependency(
                name="libbar",
                file_path="pkg.libs/libbar.so",
                digest_sha256="d" * 64,
                version=None,
            )
        ],
    )

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = [e for e in graph if e.get("type") == "software_Package"]
    phantom_pkg = next(p for p in packages if p["name"] == "libbar")
    assert phantom_pkg["software_packageVersion"] == "unknown"


def test_phantom_dependency_links_to_matching_file() -> None:
    """When a phantom dependency's file_path matches a registered project
    file, a 'contains' Relationship links the phantom package to that file."""
    files = [
        ProjectFile(
            physical_path="src/pkg.libs/libfoo.so",
            distribution_path="pkg.libs/libfoo.so",
            digest_sha256="c" * 64,
        ),
    ]
    project = ProjectMetadata(name="main-project", version="1.0.0", files=files)
    doc = DocumentModel(
        project=project,
        creation_metadata=CreationMetadata(),
        phantom_dependencies=[
            PhantomDependency(
                name="libfoo",
                file_path="pkg.libs/libfoo.so",
                digest_sha256="c" * 64,
                version=None,
            )
        ],
    )

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = [e for e in graph if e.get("type") == "software_Package"]
    phantom_pkg = next(p for p in packages if p["name"] == "libfoo")
    files_elems = [e for e in graph if e.get("type") == "software_File"]
    file_elem = next(f for f in files_elems if f["name"] == "pkg.libs/libfoo.so")

    relationships = [e for e in graph if e.get("type") == "Relationship"]
    contains = [
        r
        for r in relationships
        if r["relationshipType"] == "contains"
        and r["from"] == phantom_pkg["spdxId"]
        and file_elem["spdxId"] in r["to"]
    ]
    assert len(contains) == 1


def test_phantom_dependency_no_matching_file_no_link() -> None:
    """When a phantom dependency's file_path has no matching registered
    project file, no 'contains' relationship is created and building does
    not crash."""
    project = ProjectMetadata(name="main-project", version="1.0.0")
    doc = DocumentModel(
        project=project,
        creation_metadata=CreationMetadata(),
        phantom_dependencies=[
            PhantomDependency(
                name="libfoo",
                file_path="pkg.libs/libfoo.so",
                digest_sha256="c" * 64,
                version=None,
            )
        ],
    )

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = [e for e in graph if e.get("type") == "software_Package"]
    phantom_pkg = next(p for p in packages if p["name"] == "libfoo")

    relationships = [e for e in graph if e.get("type") == "Relationship"]
    contains_from_phantom = [
        r
        for r in relationships
        if r["relationshipType"] == "contains" and r["from"] == phantom_pkg["spdxId"]
    ]
    assert contains_from_phantom == []


# ---------------------------------------------------------------------------
# License relationship tests
# ---------------------------------------------------------------------------
# Each (model_name, license_id, hf_id) triple is taken from the model zoo in
# test_extract_huggingface.py, which records the actual values observed on
# Hugging Face Hub on 2026-05-08.  Using real identifiers ensures the assembly
# layer is exercised with the full range of license strings found in practice:
# standard SPDX IDs, custom Hugging Face identifiers, and OpenRAIL variants.
# ---------------------------------------------------------------------------

_AI_LICENSE_CASES: list[tuple[str, str, str]] = [
    # standard SPDX identifiers
    ("Kokoro-82M", "apache-2.0", "hexgrad/Kokoro-82M"),
    ("DeepSeek-R1", "mit", "deepseek-ai/DeepSeek-R1"),
    ("blip-vqa-base", "bsd-3-clause", "Salesforce/blip-vqa-base"),
    (
        "speaker-diarization-community-1",
        "cc-by-4.0",
        "pyannote/speaker-diarization-community-1",
    ),
    ("seamless-m4t-v2-large", "cc-by-nc-4.0", "facebook/seamless-m4t-v2-large"),
    (
        "wangchanglm-7.5B-sft-enth",
        "cc-by-sa-4.0",
        "pythainlp/wangchanglm-7.5B-sft-enth",
    ),
    # non-standard / custom Hugging Face license identifiers
    ("starcoder2-3b", "bigcode-openrail-m", "bigcode/starcoder2-3b"),
    ("Llama-3.2-1B", "llama3.2", "meta-llama/Llama-3.2-1B"),
    ("Hermes-3-Llama-3.2-3B", "llama3", "NousResearch/Hermes-3-Llama-3.2-3B"),
    ("Gemma-SEA-LION-v4-27B-IT", "gemma", "aisingapore/Gemma-SEA-LION-v4-27B-IT"),
    (
        "Deberta_Human_Value_Detector",
        "openrail++",
        "tum-nlp/Deberta_Human_Value_Detector",
    ),
    ("DepthPro-hf", "apple-amlr", "apple/DepthPro-hf"),
]


def _check_license_relationships(
    graph: list[dict[str, Any]], ai_pkg_id: str, license_id: str
) -> None:
    """Assert hasDeclaredLicense or hasConcludedLicense relationship exists."""
    rels = [e for e in graph if e.get("type") == "Relationship"]
    declared = [
        r
        for r in rels
        if r.get("relationshipType") == "hasDeclaredLicense"
        and r.get("from") == ai_pkg_id
    ]
    concluded = [
        r
        for r in rels
        if r.get("relationshipType") == "hasConcludedLicense"
        and r.get("from") == ai_pkg_id
    ]

    assert len(declared) + len(concluded) == 1, (
        f"expected exactly one license relationship, got {len(declared)} declared "
        f"and {len(concluded)} concluded"
    )

    license_rel = declared[0] if declared else concluded[0]
    license_spdx_id = license_rel["to"][0]
    license_elems = [
        e
        for e in graph
        if e.get("type") == "simplelicensing_SimpleLicensingText"
        and e.get("spdxId") == license_spdx_id
    ]
    assert len(license_elems) == 1
    assert license_elems[0]["simplelicensing_licenseText"] == license_id

    spdx_docs = [e for e in graph if e.get("type") == "SpdxDocument"]
    assert "simpleLicensing" in spdx_docs[0]["profileConformance"]


@pytest.mark.parametrize(
    "model_name,license_id,hf_id",
    _AI_LICENSE_CASES,
    ids=[f"{n}-{lic}" for n, lic, _ in _AI_LICENSE_CASES],
)
def test_assembler_ai_model_with_license(
    model_name: str, license_id: str, hf_id: str
) -> None:
    """AI model with a license must produce hasDeclaredLicense and
    hasConcludedLicense relationships, and simpleLicensing in profileConformance.

    Model/license pairs are taken from real Hugging Face Hub data recorded in
    the model zoo (test_extract_huggingface.py, 2026-05-08).
    """
    project = ProjectMetadata(name="ai-project", version="0.1.0")
    ai_model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.SAFETENSORS),
        name=model_name,
        license=license_id,
        provenance={
            "license": (f"Source: Hugging Face Hub ({hf_id}) | Field: cardData.license")
        },
    )
    doc = DocumentModel(
        project=project, creation_metadata=CreationMetadata(), ai_models=[ai_model]
    )

    exporter = build(doc)
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    _check_license_relationships(graph, ai_pkgs[0]["spdxId"], license_id)


# Standalone build_model() cases: real GGUF and safetensors models.
# aisingapore/Gemma-SEA-LION-v4-4B-VL-GGUF uses a custom "gemma" license;
# deepseek-ai/DeepSeek-R1 uses the standard SPDX "mit" identifier.
_BUILD_MODEL_LICENSE_CASES: list[tuple[str, str, AiModelFormat, str]] = [
    (
        "Gemma-SEA-LION-v4-4B-VL-GGUF",
        "gemma",
        AiModelFormat.GGUF,
        "aisingapore/Gemma-SEA-LION-v4-4B-VL-GGUF",
    ),
    (
        "DeepSeek-R1",
        "mit",
        AiModelFormat.SAFETENSORS,
        "deepseek-ai/DeepSeek-R1",
    ),
]


@pytest.mark.parametrize(
    "model_name,license_id,fmt,hf_id",
    _BUILD_MODEL_LICENSE_CASES,
    ids=[f"{n}-{lic}" for n, lic, _, _ in _BUILD_MODEL_LICENSE_CASES],
)
def test_build_model_with_license(
    model_name: str, license_id: str, fmt: AiModelFormat, hf_id: str
) -> None:
    """build_model() for a standalone AI model must emit license relationships
    and include simpleLicensing in profileConformance.

    Model/license pairs are taken from real Hugging Face Hub data recorded in
    the model zoo (test_extract_huggingface.py, 2026-05-08).
    """
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=fmt),
        name=model_name,
        license=license_id,
        provenance={
            "license": (f"Source: Hugging Face Hub ({hf_id}) | Field: cardData.license")
        },
    )

    exporter = build_model(model, CreationMetadata())
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    _check_license_relationships(graph, ai_pkgs[0]["spdxId"], license_id)


def test_build_model_without_license() -> None:
    """build_model() for a model with no license produces no license
    relationships and no simpleLicensing in profileConformance.

    microsoft/resnet-18 is a real Hugging Face model that does not declare a
    license in its model card, making it a realistic no-license test case.
    """
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.ONNX),
        name="resnet-18",
    )

    exporter = build_model(model, CreationMetadata())
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    rels = [e for e in graph if e.get("type") == "Relationship"]
    license_rels = [
        r
        for r in rels
        if r.get("relationshipType") in ("hasDeclaredLicense", "hasConcludedLicense")
    ]
    assert not license_rels

    spdx_docs = [e for e in graph if e.get("type") == "SpdxDocument"]
    assert "simpleLicensing" not in spdx_docs[0]["profileConformance"]


def test_build_model_external_identifiers() -> None:
    """build_model() must emit ExternalIdentifier for DOI and ExternalRef for
    arXiv paper IDs and model page URLs (external identifiers).
    """
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.SAFETENSORS),
        name="test-external-ids",
        doi="10.1234/test.doi",
        arxiv_ids=["2301.12345"],
        url="https://huggingface.co/org/test-external-ids",
    )

    exporter = build_model(model, CreationMetadata())
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    ai_pkg = ai_pkgs[0]

    # Verify DOI externalIdentifier
    ext_ids = ai_pkg.get("externalIdentifier", [])
    doi_ids = [
        i
        for i in ext_ids
        if i.get("externalIdentifierType") == "other"
        and i.get("identifier") == "10.1234/test.doi"
    ]
    assert len(doi_ids) == 1
    assert doi_ids[0].get("comment") == "DOI"

    # Verify arXiv and URL externalRef entries
    ext_refs = ai_pkg.get("externalRef", [])
    arxiv_refs = [
        r
        for r in ext_refs
        if r.get("externalRefType") == "documentation"
        and "https://arxiv.org/abs/2301.12345" in r.get("locator", [])
    ]
    assert len(arxiv_refs) == 1
    assert arxiv_refs[0].get("comment") == "arXiv:2301.12345"

    url_refs = [
        r
        for r in ext_refs
        if r.get("externalRefType") == "altWebPage"
        and "https://huggingface.co/org/test-external-ids" in r.get("locator", [])
    ]
    assert len(url_refs) == 1
    assert url_refs[0].get("comment") == "Model page URL"


def test_build_model_with_dataset_creator() -> None:
    """build_model() for a model linked to a dataset with creator metadata
    must emit an Agent element and a publishedBy Relationship
    (dataset creator attribution).
    """
    ds_meta = DatasetMetadata(name="squad", creator="Stanford NLP")
    ds_ref = DatasetReference(role="trainedOn", metadata=ds_meta)
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.SAFETENSORS),
        name="test-ds-creator",
        datasets=[ds_ref],
    )

    exporter = build_model(model, CreationMetadata())
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    agents = [e for e in graph if e.get("type") == "Agent"]
    creator_agents = [a for a in agents if a.get("name") == "Stanford NLP"]
    assert len(creator_agents) == 1
    agent_spdx_id = creator_agents[0]["spdxId"]

    ds_pkgs = [e for e in graph if e.get("type") == "dataset_DatasetPackage"]
    assert len(ds_pkgs) == 1
    ds_pkg_id = ds_pkgs[0]["spdxId"]

    rels = [e for e in graph if e.get("type") == "Relationship"]
    pub_rels = [
        r
        for r in rels
        if r.get("relationshipType") == "publishedBy"
        and r.get("from") == ds_pkg_id
        and agent_spdx_id in r.get("to", [])
    ]
    assert len(pub_rels) == 1


# ---------------------------------------------------------------------------
# generate_model_sbom() enrichment end-to-end (N3 / E1 / E2)
# ---------------------------------------------------------------------------


def test_generate_model_sbom_readme_enrichment_end_to_end() -> None:
    """A local model file with an adjacent README.md whose YAML frontmatter
    names a dataset absent from the model's own metadata: the enrichment
    run must add a new dataset_DatasetPackage + trainedOn relationship
    with a *distinct* CreationInfo (different createdUsing Tool) from the
    AI package's own, plus an "enrichment"-kind Annotation on the AI
    package recording the change."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text(
            "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
        )
        (tmppath / "pyproject.toml").write_text("[tool.pitloom.enrich]\nlocal = true\n")

        sbom_json = generate_model_sbom(model_path)

        graph = json.loads(sbom_json)["@graph"]
        ai_pkg = next(e for e in graph if e.get("type") == "ai_AIPackage")
        ai_creation_info = ai_pkg["creationInfo"]

        ds_pkgs = [e for e in graph if e.get("type") == "dataset_DatasetPackage"]
        assert len(ds_pkgs) == 1
        assert ds_pkgs[0]["name"] == "tiny-imagenet"
        dataset_creation_info = ds_pkgs[0]["creationInfo"]
        assert dataset_creation_info != ai_creation_info

        rels = [e for e in graph if e.get("type") == "Relationship"]
        trained_on = [
            r
            for r in rels
            if r.get("relationshipType") == "trainedOn"
            and r.get("from") == ai_pkg["spdxId"]
            and ds_pkgs[0]["spdxId"] in r.get("to", [])
        ]
        assert len(trained_on) == 1
        assert trained_on[0]["creationInfo"] == dataset_creation_info

        tools = {e["spdxId"]: e for e in graph if e.get("type") == "Tool"}
        creation_infos = {e["@id"]: e for e in graph if e.get("type") == "CreationInfo"}
        ai_tool_id = creation_infos[ai_creation_info]["createdUsing"][0]
        dataset_tool_id = creation_infos[dataset_creation_info]["createdUsing"][0]
        assert tools[ai_tool_id]["name"] == "Pitloom"
        assert tools[dataset_tool_id]["name"] == "pitloom.enrich.readme"
        # Same createdBy Agent on both -- enrichment doesn't invent a second
        # "Pitloom" identity, only a distinct createdUsing Tool + timestamp.
        assert (
            creation_infos[ai_creation_info]["createdBy"]
            == creation_infos[dataset_creation_info]["createdBy"]
        )

        annotations = [e for e in graph if e.get("type") == "Annotation"]
        enrichment_anns = [
            a
            for a in annotations
            if a.get("subject") == ai_pkg["spdxId"]
            and json.loads(a["statement"]).get("kind") == "enrichment"
        ]
        assert len(enrichment_anns) == 1
        statement = json.loads(enrichment_anns[0]["statement"])
        changed_fields = {c["field"] for c in statement["changes"]}
        assert changed_fields == {"license", "datasets:tiny-imagenet"}

        # The Annotation itself must carry the enrichment tool/timestamp
        # (who/when this specific fact was asserted), not the main
        # document's generic CreationInfo -- otherwise the *only* record
        # of "which enricher filled the license field in place" (N3
        # doesn't cover in-place field-fills, only new elements) is lost.
        assert enrichment_anns[0]["creationInfo"] == dataset_creation_info
        assert enrichment_anns[0]["creationInfo"] != ai_creation_info
        assert all(c["role"] == "detected" for c in statement["changes"])


def test_generate_model_sbom_field_only_enrichment_has_own_creation_info() -> None:
    """When enrichment fills only an existing element's field (no new
    dataset element -- N3 doesn't apply, there's no dataset CreationInfo
    to compare against), the E1/E2 Annotation must still carry its own
    enrichment CreationInfo (the readme enricher's tool/timestamp), not
    silently fall back to the AI package's main document CreationInfo --
    the Annotation is the *only* place this in-place field-fill's
    provenance can live."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text("---\nlicense: apache-2.0\n---\n")
        (tmppath / "pyproject.toml").write_text("[tool.pitloom.enrich]\nlocal = true\n")

        graph = json.loads(generate_model_sbom(model_path))["@graph"]

        ai_pkg = next(e for e in graph if e.get("type") == "ai_AIPackage")
        assert not [e for e in graph if e.get("type") == "dataset_DatasetPackage"]

        annotations = [e for e in graph if e.get("type") == "Annotation"]
        enrichment_anns = [
            a
            for a in annotations
            if a.get("subject") == ai_pkg["spdxId"]
            and json.loads(a["statement"]).get("kind") == "enrichment"
        ]
        assert len(enrichment_anns) == 1

        tools = {e["spdxId"]: e for e in graph if e.get("type") == "Tool"}
        creation_infos = {e["@id"]: e for e in graph if e.get("type") == "CreationInfo"}
        ann_ci_id = enrichment_anns[0]["creationInfo"]
        assert ann_ci_id != ai_pkg["creationInfo"]
        ann_tool_id = creation_infos[ann_ci_id]["createdUsing"][0]
        assert tools[ann_tool_id]["name"] == "pitloom.enrich.readme"


def test_generate_model_sbom_no_readme_no_enrichment_artifacts() -> None:
    """No adjacent README: generation succeeds with zero enrichment
    side-effects -- no extra CreationInfo, no enrichment Annotation."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())

        sbom_json = generate_model_sbom(model_path)

        graph = json.loads(sbom_json)["@graph"]
        assert not [e for e in graph if e.get("type") == "dataset_DatasetPackage"]
        assert not any(
            json.loads(e["statement"]).get("kind") == "enrichment"
            for e in graph
            if e.get("type") == "Annotation"
        )


def test_generate_model_sbom_default_off_even_with_readme() -> None:
    """No `[tool.pitloom.enrich]` config at all: enrichment stays off by
    default, even when an adjacent README has frontmatter to gap-fill from
    -- `local` must be explicitly opted into, it's not implicit."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text("---\ndatasets:\n  - tiny-imagenet\n---\n")

        sbom_json = generate_model_sbom(model_path)

        graph = json.loads(sbom_json)["@graph"]
        assert not [e for e in graph if e.get("type") == "dataset_DatasetPackage"]


def test_generate_model_sbom_enrich_local_false_disables_readme_enrichment() -> None:
    """`[tool.pitloom.enrich] local = false` in a pyproject.toml next to
    the model file turns off README enrichment explicitly (same outcome as
    the default, but exercised independently in case the default changes
    again)."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text("---\ndatasets:\n  - tiny-imagenet\n---\n")
        (tmppath / "pyproject.toml").write_text(
            "[tool.pitloom.enrich]\nlocal = false\n"
        )

        sbom_json = generate_model_sbom(model_path)

        graph = json.loads(sbom_json)["@graph"]
        assert not [e for e in graph if e.get("type") == "dataset_DatasetPackage"]


# ---------------------------------------------------------------------------
# enrich_model() -- standalone enrichment fragment
# ---------------------------------------------------------------------------


def test_enrich_model_writes_bare_graph_fragment() -> None:
    """enrich_model() must always run enrichment regardless of
    [tool.pitloom.enrich] (calling it is itself the opt-in), and its output
    must be a bare @graph fragment -- no SpdxDocument/software_Sbom/
    ai_AIPackage wrapper -- containing only what the enrichment run added."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text(
            "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
        )

        fragment_json = enrich_model(model_path)
        fragment = json.loads(fragment_json)

        assert set(fragment.keys()) == {"@context", "@graph"}
        types = {e.get("type") for e in fragment["@graph"]}
        assert "SpdxDocument" not in types
        assert "software_Sbom" not in types
        assert "ai_AIPackage" not in types

        ds_pkgs = [
            e for e in fragment["@graph"] if e.get("type") == "dataset_DatasetPackage"
        ]
        assert len(ds_pkgs) == 1
        assert ds_pkgs[0]["name"] == "tiny-imagenet"

        annotations = [e for e in fragment["@graph"] if e.get("type") == "Annotation"]
        enrichment_anns = [
            a
            for a in annotations
            if a.get("statement")
            and json.loads(a["statement"]).get("kind") == "enrichment"
        ]
        assert len(enrichment_anns) == 1
        changed_fields = {
            c["field"] for c in json.loads(enrichment_anns[0]["statement"])["changes"]
        }
        assert changed_fields == {"license", "datasets:tiny-imagenet"}


def test_enrich_model_no_readme_produces_empty_fragment() -> None:
    """No adjacent README: enrich_model() must not raise -- it writes a
    valid fragment with no enrichment content."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())

        fragment = json.loads(enrich_model(model_path))

        assert not [
            e for e in fragment["@graph"] if e.get("type") == "dataset_DatasetPackage"
        ]
        assert not [e for e in fragment["@graph"] if e.get("type") == "Annotation"]


def test_enrich_model_rejects_huggingface_source() -> None:
    """A Hugging Face source has no local enrichment to run -- HF model
    cards are already parsed natively -- so enrich_model() must reject it
    with a clear error rather than silently doing nothing."""
    with pytest.raises(ValueError, match="Hugging Face"):
        enrich_model("org/model-id")


def test_enrich_model_and_generate_model_sbom_reference_matching_ai_package_id() -> (
    None
):
    """Design invariant: a fragment from enrich_model() run against a local
    file must reference the exact same ai_AIPackage spdxId that
    generate_model_sbom(enrich=True) on the same file would assign -- both
    go through the same identity computation (_ai_model_identity), so the
    fragment's Annotation subject resolves to the base doc's real AI
    package once merged. The fragment's own newly-minted elements
    (CreationInfo, Tool, Annotation, DatasetPackage) deliberately live in a
    separate id namespace from the base doc -- see build_enrichment_fragment's
    docstring -- so only the referenced ai_AIPackage id is expected to
    match, not the fragment's full id set."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text(
            "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
        )

        fragment = json.loads(enrich_model(model_path))
        full_doc = json.loads(generate_model_sbom(model_path, enrich=True))

        full_ai_pkg = next(
            e for e in full_doc["@graph"] if e.get("type") == "ai_AIPackage"
        )
        enrichment_ann = next(
            e
            for e in fragment["@graph"]
            if e.get("type") == "Annotation"
            and json.loads(e.get("statement", "{}")).get("kind") == "enrichment"
        )
        assert enrichment_ann["subject"] == full_ai_pkg["spdxId"]


def _write_smoke_project(tmppath: Path, *, enrich_local: bool = False) -> Path:
    """Write a minimal Hatchling project with one AI model + README under
    ``src/smoke_project/`` at *tmppath*; returns the model file's path.
    Shared by the project-target enrichment tests below."""
    pkg_dir = tmppath / "src" / "smoke_project"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text("")
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    model_path = pkg_dir / "model.safetensors"
    model_path.write_bytes(fixture.read_bytes())
    (pkg_dir / "README.md").write_text(
        "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
    )
    enrich_toml = "[tool.pitloom.enrich]\nlocal = true\n" if enrich_local else ""
    (tmppath / "pyproject.toml").write_text(
        "[build-system]\n"
        'requires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n\n'
        "[project]\n"
        'name = "smoke-project"\n'
        'version = "0.1.0"\n\n'
        "[tool.hatch.build.targets.wheel]\n"
        'packages = ["src/smoke_project"]\n\n' + enrich_toml
    )
    return model_path


def test_enrich_model_project_target_matches_project_level_ai_package_id() -> None:
    """A fragment from enrich_model(project_target=...) must reference the
    same ai_AIPackage id generate_project_sbom() assigns for that model --
    project-level and single-model identity schemes differ (project name/
    version/dependencies/Merkle root vs. the model's own name/version), so
    without project_target the fragment would reference a nonexistent id
    once merged into a project-level base document (the bug this test
    guards against)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = _write_smoke_project(tmppath)

        fragment = json.loads(enrich_model(model_path, project_target=tmppath))
        full_doc = json.loads(generate_project_sbom(tmppath, enrich=True))

        full_ai_pkg = next(
            e for e in full_doc["@graph"] if e.get("type") == "ai_AIPackage"
        )
        enrichment_ann = next(
            e
            for e in fragment["@graph"]
            if e.get("type") == "Annotation"
            and json.loads(e.get("statement", "{}")).get("kind") == "enrichment"
        )
        assert enrichment_ann["subject"] == full_ai_pkg["spdxId"]


def test_enrich_model_without_project_target_mismatches_project_level_id() -> None:
    """Negative-space guard: *without* project_target, the fragment's
    referenced id must NOT match the project-level ai_AIPackage id -- if
    this test starts failing (i.e. they start matching by coincidence),
    the project_target parameter has become unnecessary and the "why" in
    build_enrichment_fragment's docstring needs re-checking, not this
    test silently loosened."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = _write_smoke_project(tmppath)

        fragment = json.loads(enrich_model(model_path))
        full_doc = json.loads(generate_project_sbom(tmppath, enrich=True))

        full_ai_pkg = next(
            e for e in full_doc["@graph"] if e.get("type") == "ai_AIPackage"
        )
        enrichment_ann = next(
            e
            for e in fragment["@graph"]
            if e.get("type") == "Annotation"
            and json.loads(e.get("statement", "{}")).get("kind") == "enrichment"
        )
        assert enrichment_ann["subject"] != full_ai_pkg["spdxId"]


def test_enrich_model_project_target_merges_correctly_end_to_end() -> None:
    """The actual regression test for the bug: a fragment generated with
    project_target, registered under [tool.pitloom.fragments], and merged
    via a real generate_project_sbom() re-run must produce a
    dataset_DatasetPackage and enrichment Annotation genuinely attached to
    the project's real ai_AIPackage -- not just matching id strings in
    isolation (see the two tests above), but surviving an actual
    merge_fragments() pass."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = _write_smoke_project(tmppath)

        fragment_path = tmppath / "model.enrich.spdx3.json"
        enrich_model(model_path, project_target=tmppath, output_path=fragment_path)
        with (tmppath / "pyproject.toml").open("a") as f:
            f.write('\n[tool.pitloom.fragments]\nfiles = ["model.enrich.spdx3.json"]\n')

        merged = json.loads(generate_project_sbom(tmppath))
        graph = merged["@graph"]

        ai_pkg = next(e for e in graph if e.get("type") == "ai_AIPackage")
        ds_pkgs = [e for e in graph if e.get("type") == "dataset_DatasetPackage"]
        assert len(ds_pkgs) == 1
        assert ds_pkgs[0]["name"] == "tiny-imagenet"

        rels = [e for e in graph if e.get("type") == "Relationship"]
        trained_on = [
            r
            for r in rels
            if r.get("relationshipType") == "trainedOn"
            and r.get("from") == ai_pkg["spdxId"]
            and ds_pkgs[0]["spdxId"] in r.get("to", [])
        ]
        assert len(trained_on) == 1

        annotations = [e for e in graph if e.get("type") == "Annotation"]
        enrichment_anns = [
            a
            for a in annotations
            if a.get("subject") == ai_pkg["spdxId"]
            and json.loads(a.get("statement", "{}")).get("kind") == "enrichment"
        ]
        assert len(enrichment_anns) == 1


def test_enrich_model_registry_pinned_id_matches_base_doc() -> None:
    """A registry-pinned ai_AIPackage id must be referenced by the
    fragment too, not the freshly computed one -- otherwise a project
    using a stable registry (--registry) gets the same dangling-reference
    bug as the project_target case, even for a single-model base doc."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(
            (
                _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
            ).read_bytes()
        )
        (tmppath / "README.md").write_text("---\ndatasets:\n  - tiny-imagenet\n---\n")

        registry_path = tmppath / "loom-ids.json"
        registry = IdRegistry.new("pinned-demo", path=registry_path)
        pinned_id = registry.register_entity("model", "ai_AIPackage")
        registry.save()

        full_doc = json.loads(
            generate_model_sbom(model_path, enrich=True, registry=registry_path)
        )
        fragment = json.loads(enrich_model(model_path, registry=registry_path))

        full_ai_pkg = next(
            e for e in full_doc["@graph"] if e.get("type") == "ai_AIPackage"
        )
        assert full_ai_pkg["spdxId"] == pinned_id

        enrichment_ann = next(
            e
            for e in fragment["@graph"]
            if e.get("type") == "Annotation"
            and json.loads(e.get("statement", "{}")).get("kind") == "enrichment"
        )
        assert enrichment_ann["subject"] == pinned_id


# ---------------------------------------------------------------------------
# Roundtrip equivalence: one-shot enrich vs. two-step enrich-then-merge
# ---------------------------------------------------------------------------


def test_enrich_then_merge_matches_one_shot_enrich() -> None:
    """generate_model_sbom(enrich=True) in one shot must produce the same
    enrichment evidence as: generate a base SBOM with enrich=False, run
    enrich_model() separately, then merge_fragments() the two -- the
    design invariant behind exposing enrichment as its own CLI/API surface
    (see the plan's Surface 2(d))."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text(
            "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
        )

        # One-shot.
        one_shot = json.loads(generate_model_sbom(model_path, enrich=True))
        one_shot_ds = {
            e["name"]
            for e in one_shot["@graph"]
            if e.get("type") == "dataset_DatasetPackage"
        }
        one_shot_ann_fields = {
            c["field"]
            for e in one_shot["@graph"]
            if e.get("type") == "Annotation" and e.get("statement")
            for c in json.loads(e["statement"]).get("changes", [])
            if json.loads(e["statement"]).get("kind") == "enrichment"
        }

        # Two-step: base without enrichment, then a separate fragment, merged.
        base_json = generate_model_sbom(model_path, enrich=False)
        fragment_json = enrich_model(model_path)
        fragment_path = tmppath / "enrichment.spdx3.json"
        fragment_path.write_text(fragment_json)

        exporter = Spdx3JsonExporter()
        # Re-deserialize the base doc into the exporter's object set, then merge.
        with tempfile.NamedTemporaryFile(
            suffix=".spdx3.json", mode="w", delete=False, dir=tmpdir
        ) as base_file:
            base_file.write(base_json)
            base_file_path = Path(base_file.name)
        with base_file_path.open("rb") as f:
            spdx3.JSONLDDeserializer().read(f, exporter.object_set)

        merge_fragments(tmppath, [fragment_path.name], exporter)
        merged = json.loads(exporter.to_json())

        merged_ds = {
            e["name"]
            for e in merged["@graph"]
            if e.get("type") == "dataset_DatasetPackage"
        }
        merged_ann_fields = {
            c["field"]
            for e in merged["@graph"]
            if e.get("type") == "Annotation" and e.get("statement")
            for c in json.loads(e["statement"]).get("changes", [])
            if json.loads(e["statement"]).get("kind") == "enrichment"
        }

        assert merged_ds == one_shot_ds == {"tiny-imagenet"}
        assert (
            merged_ann_fields
            == one_shot_ann_fields
            == {
                "license",
                "datasets:tiny-imagenet",
            }
        )


# ---------------------------------------------------------------------------
# generate_project_sbom() enrichment end-to-end (project-level N3 / E1 / E2)
# ---------------------------------------------------------------------------


def test_generate_project_sbom_enrichment_end_to_end() -> None:
    """A discovered AI model with an adjacent README.md gap-fillable via
    YAML frontmatter, plus [tool.pitloom.enrich] local = true, must produce
    the same enrichment artifacts at the project level that
    generate_model_sbom's single-model path already produces -- closing
    the gap where loom project/loom generate never ran enrichment at all."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pkg_dir = tmppath / "src" / "smoke_project"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").write_text("")
        fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
        (pkg_dir / "model.safetensors").write_bytes(fixture.read_bytes())
        (pkg_dir / "README.md").write_text(
            "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
        )
        (tmppath / "pyproject.toml").write_text(
            "[build-system]\n"
            'requires = ["hatchling"]\n'
            'build-backend = "hatchling.build"\n\n'
            "[project]\n"
            'name = "smoke-project"\n'
            'version = "0.1.0"\n\n'
            "[tool.hatch.build.targets.wheel]\n"
            'packages = ["src/smoke_project"]\n\n'
            "[tool.pitloom.enrich]\n"
            "local = true\n"
        )

        sbom_json = generate_project_sbom(tmppath)
        graph = json.loads(sbom_json)["@graph"]

        assert [e for e in graph if e.get("type") == "ai_AIPackage"]
        ds_pkgs = [e for e in graph if e.get("type") == "dataset_DatasetPackage"]
        assert len(ds_pkgs) == 1
        assert ds_pkgs[0]["name"] == "tiny-imagenet"

        annotations = [e for e in graph if e.get("type") == "Annotation"]
        enrichment_anns = [
            a
            for a in annotations
            if a.get("statement")
            and json.loads(a["statement"]).get("kind") == "enrichment"
        ]
        assert len(enrichment_anns) == 1


def test_generate_project_sbom_no_enrichment_by_default() -> None:
    """Same fixture as above but with no [tool.pitloom.enrich] config:
    project-level enrichment must stay off by default, same as every
    other surface."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pkg_dir = tmppath / "src" / "smoke_project"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").write_text("")
        fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
        (pkg_dir / "model.safetensors").write_bytes(fixture.read_bytes())
        (pkg_dir / "README.md").write_text(
            "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
        )
        (tmppath / "pyproject.toml").write_text(
            "[build-system]\n"
            'requires = ["hatchling"]\n'
            'build-backend = "hatchling.build"\n\n'
            "[project]\n"
            'name = "smoke-project"\n'
            'version = "0.1.0"\n\n'
            "[tool.hatch.build.targets.wheel]\n"
            'packages = ["src/smoke_project"]\n'
        )

        sbom_json = generate_project_sbom(tmppath)
        graph = json.loads(sbom_json)["@graph"]

        assert not [e for e in graph if e.get("type") == "dataset_DatasetPackage"]


def test_generate_project_sbom_enrich_true_overrides_config() -> None:
    """enrich=True passed to generate_project_sbom() must turn on
    enrichment even with no [tool.pitloom.enrich] config present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pkg_dir = tmppath / "src" / "smoke_project"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").write_text("")
        fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
        (pkg_dir / "model.safetensors").write_bytes(fixture.read_bytes())
        (pkg_dir / "README.md").write_text("---\ndatasets:\n  - tiny-imagenet\n---\n")
        (tmppath / "pyproject.toml").write_text(
            "[build-system]\n"
            'requires = ["hatchling"]\n'
            'build-backend = "hatchling.build"\n\n'
            "[project]\n"
            'name = "smoke-project"\n'
            'version = "0.1.0"\n\n'
            "[tool.hatch.build.targets.wheel]\n"
            'packages = ["src/smoke_project"]\n'
        )

        sbom_json = generate_project_sbom(tmppath, enrich=True)
        graph = json.loads(sbom_json)["@graph"]

        ds_pkgs = [e for e in graph if e.get("type") == "dataset_DatasetPackage"]
        assert len(ds_pkgs) == 1
        assert ds_pkgs[0]["name"] == "tiny-imagenet"


# ---------------------------------------------------------------------------
# Fixture-based end-to-end license export tests
# ---------------------------------------------------------------------------
# These tests extract real metadata from local model files in
# tests/fixtures/aimodels/,
# then assemble a standalone SPDX 3 document and verify the license
# relationships are present in the output.
#
# Many fixture files do not embed license metadata in their format (e.g. most
# Safetensors files only store {"format": "pt"} in __metadata__, and the GGUF
# extractor does not map general.license to ai_model.license).  Those fixtures
# are skipped at runtime via pytest.skip() rather than excluded from the
# parametrize list, so that newly enhanced extractors will be picked up
# automatically without any change to this test.
# ---------------------------------------------------------------------------

_FIXTURE_ROOT = Path(__file__).parent / "fixtures"
_AI_MODEL_ROOT = _FIXTURE_ROOT / "aimodels"
_AI_MODEL_DIRS = [
    "fasttext",
    "gguf",
    "hdf5",
    "keras",
    "numpy",
    "onnx",
    "pytorch",
    "pytorch_pt2",
    "safetensors",
]
_AI_MODEL_FIXTURES: list[Path] = [
    p
    for d in _AI_MODEL_DIRS
    for p in sorted((_AI_MODEL_ROOT / d).glob("*"))
    if p.is_file() and p.suffix != ""
]


@pytest.mark.parametrize(
    "fixture_path",
    _AI_MODEL_FIXTURES,
    ids=[f"{p.parent.name}/{p.name}" for p in _AI_MODEL_FIXTURES],
)
def test_fixture_license_export(fixture_path: Path) -> None:
    """Extract metadata from a fixture file and verify SPDX 3 license output.

    Skips when:
    - The fixture file is absent from the repository clone.
    - The required optional library is not installed.
    - The model format does not embed a license (``meta.license is None``).

    When a license is present, asserts that the assembled ``build_model()``
    output contains both ``hasDeclaredLicense`` and ``hasConcludedLicense``
    relationships pointing to a ``simplelicensing_SimpleLicensingText`` element
    whose ``simplelicensing_licenseText`` matches the extracted license string.
    """
    if not fixture_path.exists():
        pytest.skip(f"Fixture not found: {fixture_path}")

    try:
        meta = read_ai_model(fixture_path)
    except ImportError as exc:
        pytest.skip(str(exc))

    if meta.license is None:
        pytest.skip(f"No license metadata embedded in {fixture_path.name}")

    exporter = build_model(meta, CreationMetadata())
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    assert meta.license is not None  # type: ignore[comparison-overlap]
    _check_license_relationships(graph, ai_pkgs[0]["spdxId"], meta.license)


# ---------------------------------------------------------------------------
# assemble-layer wiring: generate_wheel_sbom() / generate_env_sbom()
# ---------------------------------------------------------------------------


def _make_wheel(tmp_path: Path, name: str, version: str) -> Path:
    """Build a minimal .whl with just a METADATA file."""
    wheel_path = tmp_path / f"{name}-{version}-py3-none-any.whl"
    metadata_body = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr(f"{name}-{version}.dist-info/METADATA", metadata_body)
        zf.writestr(f"{name}/__init__.py", "")
    return wheel_path


def test_generate_wheel_sbom_from_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate_wheel_sbom() wires read_wheel()'s extracted metadata into
    a valid SPDX 3 JSON-LD document with the expected package name/version."""
    monkeypatch.chdir(tmp_path)
    wheel_path = _make_wheel(tmp_path, "analyzed-pkg", "2.3.4")

    sbom_json = generate_wheel_sbom(wheel_path)
    data = json.loads(sbom_json)

    assert "@graph" in data
    graph = data["@graph"]
    packages = [e for e in graph if e.get("type") == "software_Package"]
    main_package = next(p for p in packages if p["name"] == "analyzed-pkg")
    assert main_package["software_packageVersion"] == "2.3.4"


def test_generate_env_sbom_mocked_pipdeptree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate_env_sbom() wires read_environment()'s pipdeptree tree
    into a valid SPDX 3 JSON-LD document containing the installed package."""
    monkeypatch.chdir(tmp_path)
    tree = [
        {
            "package": {
                "key": "requests",
                "package_name": "requests",
                "installed_version": "2.31.0",
            }
        }
    ]
    fake_result = subprocess.CompletedProcess(
        args=["pipdeptree", "--json-tree", "--all"],
        returncode=0,
        stdout=json.dumps(tree),
        stderr="",
    )

    with patch("subprocess.run", return_value=fake_result):
        sbom_json = generate_env_sbom()

    data = json.loads(sbom_json)

    assert "@graph" in data
    graph = data["@graph"]
    packages = [e for e in graph if e.get("type") == "software_Package"]
    requests_pkg = next(p for p in packages if p["name"] == "requests")
    assert requests_pkg["software_packageVersion"] == "2.31.0"


def test_generate_smart_entrypoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate() smart entrypoint auto-detects targets correctly."""
    monkeypatch.chdir(tmp_path)
    pyproject = '[project]\nname = "smart-pkg"\nversion = "0.1.0"\n'
    (tmp_path / "pyproject.toml").write_text(pyproject)

    # 1. Directory target
    proj_json = generate(tmp_path)
    assert "smart-pkg" in proj_json

    # 2. Wheel target
    wheel_path = _make_wheel(tmp_path, "smart-wheel", "1.0.0")
    wheel_json = generate(wheel_path)
    assert "smart-wheel" in wheel_json


def test_build_model_base_model_lineage() -> None:
    """build_model() must emit a stub base model ai_AIPackage and a descendantOf
    Relationship when base_model and base_model_relation are present
    (base-model lineage).
    """
    meta = AiModelMetadata(
        name="my-finetuned-model",
        base_model="Qwen/Qwen2.5-Math-1.5B",
        base_model_relation="finetune",
    )
    exporter = build_model(meta, CreationMetadata())
    graph = json.loads(exporter.to_json(pretty=True)).get("@graph", [])

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 2
    derived_pkg = next(p for p in ai_pkgs if p["name"] == "my-finetuned-model")
    base_pkg = next(p for p in ai_pkgs if p["name"] == "Qwen2.5-Math-1.5B")

    ext_refs = base_pkg.get("externalRef", [])
    assert any(
        r.get("externalRefType") == "altWebPage"
        and "https://huggingface.co/Qwen/Qwen2.5-Math-1.5B" in r.get("locator", [])
        for r in ext_refs
    )

    rels = [e for e in graph if e.get("type") == "Relationship"]
    lineage_rels = [
        r
        for r in rels
        if r.get("relationshipType") == "descendantOf"
        and r.get("from") == derived_pkg["spdxId"]
        and base_pkg["spdxId"] in r.get("to", [])
    ]
    assert len(lineage_rels) == 1
    assert lineage_rels[0].get("comment") == "base_model_relation:finetune"


# ---------------------------------------------------------------------------
# G2: declared-vs-detected license conflict, main project package
# ---------------------------------------------------------------------------


def _license_relationships(
    graph: list[dict[str, Any]], subject_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rels = [e for e in graph if e.get("type") == "Relationship"]
    declared = [
        r
        for r in rels
        if r.get("relationshipType") == "hasDeclaredLicense"
        and r.get("from") == subject_id
    ]
    concluded = [
        r
        for r in rels
        if r.get("relationshipType") == "hasConcludedLicense"
        and r.get("from") == subject_id
    ]
    return declared, concluded


def test_generate_project_sbom_license_conflict_end_to_end() -> None:
    """Declared MIT + an independently-detected Apache-2.0 LICENSE file:
    both hasDeclaredLicense and hasConcludedLicense are emitted (pointing at
    two distinct license elements), plus one G2 conflict Annotation on the
    main package."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"
license = "MIT"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)
        (tmppath / "LICENSE").write_text("Apache License\nVersion 2.0" + "x" * 200)

        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="Apache-2.0",
        ):
            sbom_json = generate_project_sbom(tmppath)

        graph = json.loads(sbom_json)["@graph"]
        main_package = next(
            e
            for e in graph
            if e.get("type") == "software_Package" and e["name"] == "test-package"
        )
        declared, concluded = _license_relationships(graph, main_package["spdxId"])
        assert len(declared) == 1
        assert len(concluded) == 1

        license_elems = {
            e["spdxId"]: e
            for e in graph
            if e.get("type") == "simplelicensing_SimpleLicensingText"
        }
        declared_license = license_elems[declared[0]["to"][0]]
        concluded_license = license_elems[concluded[0]["to"][0]]
        assert declared_license["simplelicensing_licenseText"] == "MIT"
        assert concluded_license["simplelicensing_licenseText"] == "Apache-2.0"
        assert declared_license["spdxId"] != concluded_license["spdxId"]

        annotations = [e for e in graph if e.get("type") == "Annotation"]
        conflict_anns = [
            a
            for a in annotations
            if a.get("subject") == main_package["spdxId"]
            and json.loads(a["statement"]).get("kind") == "conflict"
        ]
        assert len(conflict_anns) == 1
        statement = json.loads(conflict_anns[0]["statement"])
        assert statement["field"] == "license"
        roles = {c["role"] for c in statement["candidates"]}
        assert roles == {"declared", "detected"}


def test_generate_project_sbom_license_conflict_flags_declared_normalization() -> None:
    """Declared "mit" (valid but non-canonically cased) + a genuinely
    conflicting detected Apache-2.0: the conflict Annotation's declared
    candidate ``source`` is flagged with the raw value normalize_license_
    expression() rewrote it from, plus the py-spdx-license version that did
    it -- wiring the previously-dead _PY_SPDX_LICENSE_VERSION into actual
    output (not just the case-only-agreement path, which never reaches the
    conflict branch at all)."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"
license = "mit"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)
        (tmppath / "LICENSE").write_text("Apache License\nVersion 2.0" + "x" * 200)

        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="Apache-2.0",
        ):
            sbom_json = generate_project_sbom(tmppath)

        graph = json.loads(sbom_json)["@graph"]
        main_package = next(
            e
            for e in graph
            if e.get("type") == "software_Package" and e["name"] == "test-package"
        )
        annotations = [e for e in graph if e.get("type") == "Annotation"]
        conflict_anns = [
            a
            for a in annotations
            if a.get("subject") == main_package["spdxId"]
            and json.loads(a["statement"]).get("kind") == "conflict"
        ]
        assert len(conflict_anns) == 1
        statement = json.loads(conflict_anns[0]["statement"])
        declared_candidate = next(
            c for c in statement["candidates"] if c["role"] == "declared"
        )
        assert declared_candidate["value"] == "MIT"
        assert "Normalized-From: mit" in declared_candidate["source"]
        assert "Normalizer: py-spdx-license==" in declared_candidate["source"]


def test_generate_project_sbom_license_agrees_no_conflict_annotation() -> None:
    """Declared and independently-detected license agree: both relationships
    still emitted, pointing at the *same* element, but no conflict Annotation."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"
license = "MIT"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)
        (tmppath / "LICENSE").write_text("MIT License\n\nPermission" + "x" * 200)

        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="MIT",
        ):
            sbom_json = generate_project_sbom(tmppath)

        graph = json.loads(sbom_json)["@graph"]
        main_package = next(
            e
            for e in graph
            if e.get("type") == "software_Package" and e["name"] == "test-package"
        )
        declared, concluded = _license_relationships(graph, main_package["spdxId"])
        assert len(declared) == 1
        assert len(concluded) == 1
        assert declared[0]["to"][0] == concluded[0]["to"][0]


def test_generate_project_sbom_license_case_only_difference_not_a_conflict() -> None:
    """Regression: a declared `license = "mit"` (valid but non-canonically
    cased -- kept verbatim since Pitloom never rewrites a bare SPDX id) and
    an independently-detected canonical "MIT" from the LICENSE file must be
    recognized as the *same* license, not flagged as G2 conflict. Before the
    canonicalization fix, this produced a spurious conflict Annotation and
    two separate license elements for what is one license."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"
license = "mit"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)
        (tmppath / "LICENSE").write_text("MIT License\n\nPermission" + "x" * 200)

        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="MIT",
        ):
            sbom_json = generate_project_sbom(tmppath)

        graph = json.loads(sbom_json)["@graph"]
        main_package = next(
            e
            for e in graph
            if e.get("type") == "software_Package" and e["name"] == "test-package"
        )
        declared, concluded = _license_relationships(graph, main_package["spdxId"])
        assert len(declared) == 1
        assert len(concluded) == 1
        assert declared[0]["to"][0] == concluded[0]["to"][0]

        license_elems = [
            e for e in graph if e.get("type") == "simplelicensing_SimpleLicensingText"
        ]
        assert len(license_elems) == 1
        assert license_elems[0]["simplelicensing_licenseText"] == "MIT"

        annotations = [e for e in graph if e.get("type") == "Annotation"]
        conflict_anns = [
            a
            for a in annotations
            if json.loads(a["statement"]).get("kind") == "conflict"
        ]
        assert conflict_anns == []

        annotations = [e for e in graph if e.get("type") == "Annotation"]
        conflict_anns = [
            a
            for a in annotations
            if json.loads(a["statement"]).get("kind") == "conflict"
        ]
        assert conflict_anns == []


def test_generate_project_sbom_license_declared_only_no_license_file() -> None:
    """Declared license, no LICENSE file in the project: unchanged
    single-relationship behavior (regression check against pre-G2 output)."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"
license = "MIT"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)

        sbom_json = generate_project_sbom(tmppath)

        graph = json.loads(sbom_json)["@graph"]
        main_package = next(
            e
            for e in graph
            if e.get("type") == "software_Package" and e["name"] == "test-package"
        )
        declared, concluded = _license_relationships(graph, main_package["spdxId"])
        assert len(declared) == 1
        assert len(concluded) == 0


def test_generate_project_sbom_license_conflict_byte_identical_across_runs() -> None:
    """Determinism: two independent generations from the same input produce
    byte-identical output, including the new conflict Annotation."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"
license = "MIT"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject_content)
        (tmppath / "LICENSE").write_text("Apache License\nVersion 2.0" + "x" * 200)

        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="Apache-2.0",
        ):
            creation_metadata = CreationMetadata(
                creation_datetime="2026-01-01T00:00:00Z"
            )
            sbom_json_1 = generate_project_sbom(
                tmppath, creation_metadata=creation_metadata
            )
            sbom_json_2 = generate_project_sbom(
                tmppath, creation_metadata=creation_metadata
            )

        assert sbom_json_1 == sbom_json_2
