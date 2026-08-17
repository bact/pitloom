# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.assemble.generate_project_sbom / build(): creator/tool
multiplicity, sentimentdemo-shaped structure, dependency-name parsing,
external SBOM fragments, setup.cfg-only projects, and preparsed
metadata/config passthrough.

See also: tests/core/test_generator_project.py for basic generation,
main-package PURL, output path, creation comment/tool summary, and
createdBy creator-type handling. tests/core/test_generator_project_enrichment.py
for project-level enrichment and license-conflict-detection tests.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.__about__ import __version__
from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3.document import build
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata, Creator, Tool
from pitloom.core.document import DocumentModel
from pitloom.core.models import generate_spdx_id
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

from .conftest import _creation_agents


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
