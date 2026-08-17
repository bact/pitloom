# ruff: noqa: F403, F405
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.__about__ import __version__
from pitloom.assemble import (
    generate_project_sbom,
)
from pitloom.assemble.spdx3.document import (
    _magika_version,
    build,
)
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata, Creator, Tool
from pitloom.core.document import DocumentModel
from pitloom.core.models import generate_spdx_id
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

from .conftest import *


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
    """_magika_version() must only hit importlib.metadata once per process,
    not once per magika-detected file -- real disk I/O otherwise repeated
    for a value that can't change mid-process."""
    _magika_version.cache_clear()
    call_count = 0

    # pylint: disable=unused-argument
    def _fake_pkg_version(name: str) -> str:
        nonlocal call_count
        call_count += 1
        return "1.2.3"

    monkeypatch.setattr(
        "pitloom.assemble.spdx3.document._pkg_version", _fake_pkg_version
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


def test_generate_project_sbom_enrichment_end_to_end() -> None:
    """A discovered AI model with an adjacent README.md gap-fillable via
    YAML frontmatter, plus [tool.pitloom] enrich = true, must produce
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
            "[tool.pitloom]\n"
            "enrich = true\n"
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
    """Same fixture as above but with no [tool.pitloom] enrich config:
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
    enrichment even with no [tool.pitloom] enrich config present."""
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
