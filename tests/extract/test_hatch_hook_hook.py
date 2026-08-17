# ruff: noqa: F403, F405
from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import rfc8785
from spdx_python_model.bindings import v3_0_1 as spdx3  # noqa: E402

from pitloom.__about__ import __version__  # noqa: E402
from pitloom.core.models import generate_spdx_id  # noqa: E402
from pitloom.export.spdx3_json import (  # noqa: E402
    Spdx3JsonExporter,
    require_spdx_id,
)

from .conftest import *


def test_hook_initialize_stages_sbom() -> None:
    """initialize() must stage the SBOM file and store its path."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        assert hook._sbom_staging_path.exists()
        assert hook._sbom_staging_path.stat().st_size > 0

        # Cleanup without a real wheel (no injection)
        hook.finalize("standard", build_data, "")


def test_hook_sbom_is_valid_json() -> None:
    """The staged SBOM must be valid JSON-LD with @context and @graph."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        data = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))
        assert "@context" in data
        assert "@graph" in data

        hook.finalize("standard", build_data, "")


def test_hook_creator_name_propagated() -> None:
    """[[tool.pitloom.creator]] name must appear in the SBOM graph."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path,
            '[[tool.pitloom.creator]]\nname = "Test Creator"\n',
        )

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        data = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))
        graph = data["@graph"]
        names = [e.get("name") for e in graph if e.get("type") == "Person"]
        assert "Test Creator" in names

        hook.finalize("standard", build_data, "")


def test_hook_organization_creator_from_config() -> None:
    """[[tool.pitloom.creator]] type = organization emits an
    Organization (not a Person) in the SBOM graph."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path,
            '[[tool.pitloom.creator]]\nname = "Acme Corp"\ntype = "organization"\n',
        )

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        graph = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))[
            "@graph"
        ]
        orgs = [e.get("name") for e in graph if e.get("type") == "Organization"]
        assert orgs == ["Acme Corp"]
        assert not [e for e in graph if e.get("type") == "Person"]

        hook.finalize("standard", build_data, "")


def test_hook_multiple_creators_appear_in_graph() -> None:
    """Multiple [[tool.pitloom.creator]] tables all appear in the SBOM
    @graph, as their respective Agent subclasses."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path,
            "[[tool.pitloom.creator]]\n"
            'name = "Acme Corp"\n'
            'type = "organization"\n'
            "\n"
            "[[tool.pitloom.creator]]\n"
            'name = "Alice"\n'
            'email = "alice@example.com"\n',
        )

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        graph = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))[
            "@graph"
        ]
        orgs = [e.get("name") for e in graph if e.get("type") == "Organization"]
        persons = [e.get("name") for e in graph if e.get("type") == "Person"]
        assert orgs == ["Acme Corp"]
        assert persons == ["Alice"]

        creation_infos = [e for e in graph if e.get("type") == "CreationInfo"]
        assert len(creation_infos) == 1
        assert len(creation_infos[0]["createdBy"]) == 2

        hook.finalize("standard", build_data, "")


@pytest.mark.parametrize(
    ("creator_type", "expected_element_type"),
    [
        ("software-agent", "SoftwareAgent"),
        ("agent", "Agent"),
    ],
)
def test_hook_software_agent_and_generic_agent_creator_from_config(
    creator_type: str, expected_element_type: str
) -> None:
    """[[tool.pitloom.creator]] type also allows a named
    SoftwareAgent or generic Agent, not just Person/Organization."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path,
            f'[[tool.pitloom.creator]]\nname = "CI Bot"\ntype = "{creator_type}"\n',
        )

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        graph = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))[
            "@graph"
        ]
        matches = [
            e.get("name") for e in graph if e.get("type") == expected_element_type
        ]
        assert "CI Bot" in matches

        hook.finalize("standard", build_data, "")


def test_hook_default_creator_is_software_agent() -> None:
    """With no [[tool.pitloom.creator]], the hook records the
    SoftwareAgent "Pitloom" as the createdBy agent."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        graph = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))[
            "@graph"
        ]
        agents = [e for e in graph if e.get("type") == "SoftwareAgent"]
        assert [a["name"] for a in agents] == ["Pitloom"]
        assert not [e for e in graph if e.get("type") == "Person"]

        hook.finalize("standard", build_data, "")


def test_hook_creation_comment_and_tool_summary() -> None:
    """Hook must stamp a build-hook comment and a Pitloom-versioned Tool.summary."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        data = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))
        graph = data["@graph"]

        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        assert creation_infos[0]["comment"] == (
            "Generated via Pitloom Hatchling build hook (PEP 770)"
        )

        tool_elements = [e for e in graph if e["type"] == "Tool"]
        assert len(tool_elements) == 1
        assert tool_elements[0]["summary"] == f"Pitloom {__version__}"

        hook.finalize("standard", build_data, "")


def test_hook_custom_basename_stored() -> None:
    """A custom [tool.pitloom] sbom-basename must be reflected in the staged
    filename."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path, '[tool.pitloom]\nsbom-basename = "custom"\n'
        )

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_filename == "custom.spdx3.json"
        assert hook._sbom_staging_path is not None
        assert hook._sbom_staging_path.name == "custom.spdx3.json"

        hook.finalize("standard", build_data, "")


def test_hook_disabled_skips_generation() -> None:
    """When enabled=false, initialize() must not stage any file."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {"enabled": False})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is None
        assert hook._staging_dir is None


def test_hook_finalize_cleans_up() -> None:
    """finalize() must remove the temporary staging directory."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        staged = hook._sbom_staging_path
        assert staged is not None and staged.exists()

        # Pass empty artifact_path to skip wheel injection
        hook.finalize("standard", build_data, "")

        assert not staged.exists()
        assert hook._staging_dir is None
        assert hook._sbom_staging_path is None


def test_hook_finalize_idempotent() -> None:
    """Calling finalize() twice must not raise."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)
        hook.finalize("standard", build_data, "")
        hook.finalize("standard", build_data, "")  # second call must be a no-op


def test_hook_sbom_files_populated() -> None:
    """initialize() must append the staged path to build_data['sbom_files']."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert "sbom_files" in build_data
        assert len(build_data["sbom_files"]) == 1
        staged = Path(build_data["sbom_files"][0])
        assert staged.exists()
        assert staged.name == "testpkg-0.1.0.spdx3.json"

        hook.finalize("standard", build_data, "")


def test_hook_sbom_files_custom_basename() -> None:
    """[tool.pitloom] sbom-basename must determine the filename appended to
    sbom_files."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path, '[tool.pitloom]\nsbom-basename = "custom"\n'
        )

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert len(build_data["sbom_files"]) == 1
        assert Path(build_data["sbom_files"][0]).name == "custom.spdx3.json"

        hook.finalize("standard", build_data, "")


def test_hook_sbom_files_appended_to_existing() -> None:
    """initialize() must append to an existing sbom_files list, not replace it."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {"sbom_files": ["/existing/other.cdx.json"]}
        hook.initialize("standard", build_data)

        assert len(build_data["sbom_files"]) == 2
        assert build_data["sbom_files"][0] == "/existing/other.cdx.json"

        hook.finalize("standard", build_data, "")


def test_hook_with_pitloom_fragments() -> None:
    """Fragments listed under [tool.pitloom] are merged."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path, '[tool.pitloom.fragment]\nfiles = ["frag.json"]\n'
        )

        # Build a valid fragment via Spdx3JsonExporter
        doc_uuid = "test-frag-uuid"
        ci = spdx3.CreationInfo(
            specVersion="3.0.1",
            created=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        person = spdx3.Person(
            spdxId=generate_spdx_id("Person", "frag-author", doc_uuid),
            name="Frag Author",
            creationInfo=ci,
        )
        ci.createdBy = [require_spdx_id(person)]
        pkg = spdx3.software_Package(
            spdxId=generate_spdx_id("Package", "fragment-lib", doc_uuid),
            name="fragment-lib",
            creationInfo=ci,
        )
        frag_exporter = Spdx3JsonExporter()
        frag_exporter.add_person(person)
        frag_exporter.add_package(pkg)
        frag_path = tmp_path / "frag.json"
        frag_path.write_text(frag_exporter.to_json(), encoding="utf-8")

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        data = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))
        names = [e.get("name") for e in data["@graph"]]
        assert "fragment-lib" in names

        hook.finalize("standard", build_data, "")


def test_hook_missing_fragment_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-existent fragment path logs a warning rather than raising."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path, '[tool.pitloom.fragment]\nfiles = ["does_not_exist.json"]\n'
        )

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}

        with caplog.at_level(logging.WARNING):
            hook.initialize("standard", build_data)

        assert any("does_not_exist.json" in msg for msg in caplog.messages)
        # SBOM is still generated despite the missing fragment
        assert hook._sbom_staging_path is not None

        hook.finalize("standard", build_data, "")


def test_hook_with_sampleproject_fixture() -> None:
    """initialize() succeeds on the real 'sampleproject-hatchling' fixture."""
    fixture_dir = (
        Path(__file__).parent.parent
        / "fixtures"
        / "projects"
        / "sampleproject-hatchling"
    )
    if not fixture_dir.exists():
        pytest.skip("sampleproject-hatchling fixture not found")

    hook = make_hook(str(fixture_dir), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)

    assert hook._sbom_staging_path is not None
    data = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))
    graph = data["@graph"]
    pkg_names = [e.get("name") for e in graph if e.get("type") == "software_Package"]
    # metadata_from_hatchling() uses core.raw_name (the un-normalized name),
    # not Hatchling's PEP-503-normalized core.name, so the package name here
    # is "sampleproject_hatchling" -- exactly the spelling written in
    # pyproject.toml's [project] name -- matching what the CLI (read_pyproject)
    # would report for the same project.
    # When change this line, also change the corresponding Verify SBOM step
    # in .github/workflows/hatch-integration.yml
    assert "sampleproject_hatchling" in pkg_names

    hook.finalize("standard", build_data, "")


def test_hook_bundled_binary_produces_phantom_dependency() -> None:
    """A wheel containing an auditwheel-style bundled .so (under a
    <package>.libs/ directory) must produce a phantom-dependency
    software_Package in the SBOM graph, via find_phantom_dependencies()
    wired into _build_document_model()."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path,
            "[tool.hatch.build.targets.wheel]\npackages = "
            '["testpkg", "testpkg.libs"]\n',
        )
        (tmp_path / "testpkg").mkdir()
        (tmp_path / "testpkg" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "testpkg.libs").mkdir()
        (tmp_path / "testpkg.libs" / "libfoo-abc123.so").write_bytes(
            b"\x7fELF fake binary content"
        )

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        data = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))
        graph = data["@graph"]

        packages = [e for e in graph if e.get("type") == "software_Package"]
        phantom_pkg = next(p for p in packages if p["name"] == "libfoo-abc123")
        assert phantom_pkg["comment"].startswith(
            "Metadata provenance: package: Phantom dependency"
        )

        main_package = next(p for p in packages if p["name"] == "testpkg")
        relationships = [e for e in graph if e.get("type") == "Relationship"]
        depends_on = [
            r
            for r in relationships
            if r["relationshipType"] == "dependsOn"
            and r["from"] == main_package["spdxId"]
            and phantom_pkg["spdxId"] in r["to"]
        ]
        assert len(depends_on) == 1

        hook.finalize("standard", build_data, "")


def test_hook_enrichment_produces_dataset_and_annotation() -> None:
    """A discovered AI model file with an adjacent README.md whose YAML
    frontmatter has a dataset gap, plus [tool.pitloom] enrich = true,
    must produce the same enrichment artifacts (dataset_DatasetPackage,
    "enrichment"-kind Annotation) the build hook already produces via
    build() -- confirming the hook auto-inherits project-level enrichment
    with no new hook-specific config key."""
    fixture_model = (
        Path(__file__).parent.parent
        / "fixtures"
        / "aimodels"
        / "safetensors"
        / "phi-tiny-random.safetensors"
    )
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path,
            '[tool.hatch.build.targets.wheel]\npackages = ["testpkg"]\n'
            "\n[tool.pitloom]\nenrich = true\n",
        )
        (tmp_path / "testpkg").mkdir()
        (tmp_path / "testpkg" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "testpkg" / "model.safetensors").write_bytes(
            fixture_model.read_bytes()
        )
        (tmp_path / "testpkg" / "README.md").write_text(
            "---\ndatasets:\n  - tiny-imagenet\n---\n", encoding="utf-8"
        )

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        data = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))
        graph = data["@graph"]

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

        hook.finalize("standard", build_data, "")


def test_hook_no_enrichment_by_default() -> None:
    """Same fixture as above but with no [tool.pitloom] enrich config at
    all: enrichment must stay off by default, same as every other surface."""
    fixture_model = (
        Path(__file__).parent.parent
        / "fixtures"
        / "aimodels"
        / "safetensors"
        / "phi-tiny-random.safetensors"
    )
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path, '[tool.hatch.build.targets.wheel]\npackages = ["testpkg"]\n'
        )
        (tmp_path / "testpkg").mkdir()
        (tmp_path / "testpkg" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "testpkg" / "model.safetensors").write_bytes(
            fixture_model.read_bytes()
        )
        (tmp_path / "testpkg" / "README.md").write_text(
            "---\ndatasets:\n  - tiny-imagenet\n---\n", encoding="utf-8"
        )

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        data = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))
        graph = data["@graph"]

        assert not [e for e in graph if e.get("type") == "dataset_DatasetPackage"]

        hook.finalize("standard", build_data, "")


def test_hook_honours_provenance_format_annotation() -> None:
    """The build hook must thread [tool.pitloom.provenance] format/schema
    through to the assembler -- with format = "annotation", the staged SBOM
    carries provenance as Core Annotation elements and the main package's
    comment is not set from provenance. The ``authors`` entry gives a
    high-signal (inferred copyright) field under the default minimal detail --
    trivial name/version reads from the build backend are dropped."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(
            tmp_path,
            """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "testpkg"
version = "0.1.0"
description = "Test package."
requires-python = ">=3.10"
authors = [{name = "Jane Doe"}]

[tool.pitloom.provenance]
format = "annotation"
""",
        )

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        data = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))
        graph = data["@graph"]

        main_package = next(
            e
            for e in graph
            if e.get("type") == "software_Package" and e.get("name") == "testpkg"
        )
        assert "comment" not in main_package or main_package["comment"] is None

        annotations = [e for e in graph if e.get("type") == "Annotation"]
        main_annotations = [
            a for a in annotations if a.get("subject") == main_package["spdxId"]
        ]
        assert len(main_annotations) == 1
        assert main_annotations[0]["contentType"] == "application/json"
        statement = json.loads(main_annotations[0]["statement"])
        # Minimal keeps the inferred copyright, drops trivial name/version.
        assert set(statement["fields"]) == {"copyright_text"}

        hook.finalize("standard", build_data, "")


def test_hook_uses_hatchling_resolved_dynamic_version() -> None:
    """initialize() must use ``self.metadata.version`` -- the version
    Hatchling resolves via its configured version source -- rather than a
    naive re-parse of ``pyproject.toml``.

    The 'sampleproject-hatchling-dynver' fixture computes its version at
    import time (``__version__ = "1.0." + str(2 + 3)``) via a
    ``[tool.hatch.version] source = "code"`` expression, so only Hatchling's
    own resolution yields the correct value.
    """
    fixture_dir = (
        Path(__file__).parent.parent
        / "fixtures"
        / "projects"
        / "sampleproject-hatchling-dynver"
    )
    if not fixture_dir.exists():
        pytest.skip("sampleproject-hatchling-dynver fixture not found")

    hook = make_hook(str(fixture_dir), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)

    assert hook._sbom_staging_path is not None
    data = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))
    graph = data["@graph"]
    packages = [e for e in graph if e.get("type") == "software_Package"]
    # metadata_from_hatchling() uses core.raw_name, so the package name is
    # "sampleproject_hatchling_dynver" -- the un-normalized spelling written
    # in pyproject.toml's [project] name -- while the PURL is still
    # PEP-503-canonicalized (build_pypi_purl -> canonicalize_name()).
    (main_pkg,) = [
        p for p in packages if p.get("name") == "sampleproject_hatchling_dynver"
    ]
    assert main_pkg["software_packageVersion"] == "1.0.5"
    assert main_pkg["software_packageUrl"] == (
        "pkg:pypi/sampleproject-hatchling-dynver@1.0.5"
    )

    hook.finalize("standard", build_data, "")


def test_hook_skips_non_wheel_target() -> None:
    """initialize() must do nothing for targets other than 'wheel' (e.g. sdist)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {}, target_name="sdist")
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is None
        assert hook._staging_dir is None
        assert "sbom_files" not in build_data


def test_hook_initialize_raises_for_old_hatchling() -> None:
    """initialize() must surface the version-gate error for a wheel target."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        with (
            patch("pitloom.plugins.hatch._pkg_version", return_value="1.27.0"),
            pytest.raises(RuntimeError, match="too old for PEP 770 SBOM embedding"),
        ):
            hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is None
        assert hook._staging_dir is None


def test_hook_skips_hatchling_check_for_non_wheel_target() -> None:
    """The version gate only applies to wheel builds; sdist must not raise
    even under an Hatchling older than the minimum."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {}, target_name="sdist")
        build_data: dict[str, Any] = {}
        with patch("pitloom.plugins.hatch._pkg_version", return_value="1.27.0"):
            hook.initialize("standard", build_data)  # must not raise

        assert hook._sbom_staging_path is None


def test_hook_invalid_config_raises_before_io() -> None:
    """initialize() raises ValueError on bad config without touching the filesystem."""
    # No pyproject.toml written -- error must occur before reading it
    with tempfile.TemporaryDirectory() as tmp:
        hook = make_hook(tmp, {"enabled": "yes"})
        build_data: dict[str, Any] = {}
        with pytest.raises(ValueError, match="'enabled' must be a boolean"):
            hook.initialize("standard", build_data)

        assert hook._staging_dir is None
        assert hook._sbom_staging_path is None


def test_hook_sbom_is_compact_despite_pretty_config() -> None:
    """The SBOM staged for the wheel must be RFC 8785 (JCS) canonical even when
    ``[tool.pitloom] pretty = true`` is set in the project's pyproject.toml.

    Compact, canonically-ordered output is required by the SPDX JSON
    Serialization Scheme for embedded SBOMs (PEP 770).
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path, PYPROJECT_WITH_PRETTY)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        raw = hook._sbom_staging_path.read_bytes()

        # Must be byte-for-byte identical to RFC 8785 canonical form.
        data = json.loads(raw)
        assert raw == rfc8785.dumps(data), (
            "Embedded SBOM is not RFC 8785/JCS canonical. "
            "The [tool.pitloom] pretty=true setting must be ignored by the hook."
        )

        hook.finalize("standard", build_data, "")
