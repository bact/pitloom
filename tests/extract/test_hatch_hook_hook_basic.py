# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Pitloom Hatchling build hook (pitloom.plugins.hatch):
lifecycle basics, creator/creation metadata, fragments.

See also: test_hatch_hook_hook_integration.py for fixture-driven and
version-gate integration tests.
"""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3  # noqa: E402

from pitloom.__about__ import __version__  # noqa: E402
from pitloom.core.models import generate_spdx_id  # noqa: E402
from pitloom.export.spdx3_json import (  # noqa: E402
    Spdx3JsonExporter,
    require_spdx_id,
)

from .conftest import (
    make_hook,
    write_pyproject,
    write_pyproject_with_pitloom_config,
)

pytest.importorskip("hatchling", reason="hatchling is required for hook tests")


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
