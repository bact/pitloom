# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.assemble.generate_project_sbom / build(): structure,
dependency-name parsing, external SBOM fragments, setup.cfg, and preparsed metadata.

See also:
- :mod:`tests.core.generator.test_generator_project` for basic
  generation and PURL.
- :mod:`tests.core.generator.test_generator_project_creators` for
  creators and tools.
- :mod:`tests.core.generator.test_generator_project_enrichment` for
  project-level enrichment.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3.document import build
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.models import generate_spdx_id
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id


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
    """Dependency names must be clean even with markers and multi-clause specifiers."""
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
            purl = pkg["software_packageUrl"]
            expected = f"pkg:pypi/{name}" + (
                "" if version == "unknown" else f"@{version}"
            )
            assert purl == expected


def test_build_main_package_noassertion_license_when_undeclared() -> None:
    """The main project package must assert hasDeclaredLicense: NOASSERTION."""
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
    assert "simpleLicensing" not in spdx_docs[0]["profileConformance"]


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

[tool.pitloom.fragment]
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

        graph = sbom_data["@graph"]
        element_types = {elem["type"] for elem in graph}

        assert "ai_AIPackage" in element_types
        assert "dataset_DatasetPackage" in element_types
        assert "software_Package" in element_types

        ai_packages = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert ai_packages[0]["name"] == "cool-ai-model"

        dataset_packages = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert dataset_packages[0]["name"] == "cool-dataset"


def test_generate_project_sbom_setup_cfg_only_project() -> None:
    """generate_project_sbom() must support projects with no pyproject.toml at all."""
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
    """project_metadata and pitloom_config must be given together."""
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
