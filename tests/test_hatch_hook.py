# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Pitloom Hatchling build hook (pitloom.plugins.hatch)."""

# Tests necessarily access private attributes of PitloomBuildHook to inspect
# internal state (white-box testing) and to bypass BuildHookInterface.__init__.
# pylint: disable=protected-access

from __future__ import annotations

import json
import logging
import tempfile
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import rfc8785

# Skip the entire module if hatchling is not installed.
pytest.importorskip("hatchling", reason="hatchling is required for hook tests")

# Imports below require hatchling (guarded by importorskip above).
# pylint: disable=wrong-import-position
import hatchling.metadata.core as hatchling_metadata_core  # noqa: E402
from hatchling.plugin.manager import PluginManager  # noqa: E402
from spdx_python_model.bindings import v3_0_1 as spdx3  # noqa: E402

from pitloom.__about__ import __version__  # noqa: E402
from pitloom.core.models import compute_doc_uuid, generate_spdx_id  # noqa: E402
from pitloom.export.spdx3_json import (  # noqa: E402
    Spdx3JsonExporter,
    require_spdx_id,
)
from pitloom.extract.hatchling import metadata_from_hatchling  # noqa: E402
from pitloom.extract.pyproject import read_pyproject  # noqa: E402
from pitloom.plugins.hatch import (  # noqa: E402
    PitloomBuildHook,
    _validate_config,
)

# pylint: enable=wrong-import-position

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "testpkg"
version = "0.1.0"
description = "Test package."
requires-python = ">=3.10"
"""


def make_hook(
    root: str,
    config: dict[str, Any],
    target_name: str = "wheel",
) -> PitloomBuildHook:
    """Construct a ``PitloomBuildHook`` without invoking
    ``BuildHookInterface.__init__``.

    ``BuildHookInterface`` stores ``root``, ``config``, ``build_config``,
    ``project_metadata``, and ``target_name`` under mangled names and exposes them as
    read-only properties, so we set the mangled attributes directly via
    ``object.__setattr__``.  A bare ``SimpleNamespace`` satisfies
    ``build_config`` -- ``initialize()`` does not access it (file discovery
    uses ``WheelBuilder`` directly), but the slot must exist to prevent
    ``AttributeError`` from base-class property access.

    ``project_metadata`` is a real ``hatchling.metadata.core.ProjectMetadata`` bound
    to *root*, matching what Hatchling itself passes to a build hook; its
    properties are evaluated lazily, so constructing it does not require
    ``root`` to contain a valid ``pyproject.toml`` yet.
    """
    hook: PitloomBuildHook = object.__new__(PitloomBuildHook)
    object.__setattr__(hook, "_BuildHookInterface__root", root)
    object.__setattr__(hook, "_BuildHookInterface__config", config)
    object.__setattr__(
        hook, "_BuildHookInterface__build_config", types.SimpleNamespace()
    )
    object.__setattr__(
        hook,
        "_BuildHookInterface__metadata",
        hatchling_metadata_core.ProjectMetadata(root, PluginManager()),
    )
    object.__setattr__(hook, "_BuildHookInterface__target_name", target_name)
    hook._staging_dir = None
    hook._sbom_staging_path = None
    hook._sbom_filename = "sbom.spdx3.json"
    return hook


def write_pyproject(directory: Path, content: str = MINIMAL_PYPROJECT) -> None:
    """Write ``content`` as ``pyproject.toml`` in ``directory``."""
    (directory / "pyproject.toml").write_text(content, encoding="utf-8")


def write_pyproject_with_pitloom_config(directory: Path, extra_toml: str) -> None:
    """Write ``MINIMAL_PYPROJECT`` plus *extra_toml* (e.g. a ``[tool.pitloom]``
    or ``[tool.pitloom.creation]`` block) as ``pyproject.toml``."""
    write_pyproject(directory, MINIMAL_PYPROJECT + "\n" + extra_toml)


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def test_validate_config_defaults_pass() -> None:
    """Empty config (all defaults) must not raise."""
    _validate_config({})


def test_validate_config_valid_values_pass() -> None:
    """The only supported key, 'enabled', must not raise."""
    _validate_config({"enabled": True})


@pytest.mark.parametrize(
    ("field", "bad_value", "match"),
    [
        ("enabled", "yes", "'enabled' must be a boolean"),
        ("enabled", 1, "'enabled' must be a boolean"),
    ],
)
def test_validate_config_invalid_raises(field: str, bad_value: Any, match: str) -> None:
    """Invalid field type or value must raise ``ValueError`` with a clear message."""
    with pytest.raises(ValueError, match=match):
        _validate_config({field: bad_value})


@pytest.mark.parametrize(
    ("key", "new_location"),
    [
        ("sbom-basename", r"\[tool\.pitloom\] sbom-basename"),
        ("fragments", r"\[tool\.pitloom\.fragments\] files"),
        ("creator-name", r"\[\[tool\.pitloom\.creator\]\]"),
        ("creator-email", r"\[\[tool\.pitloom\.creator\]\]"),
        ("creator-type", r"\[\[tool\.pitloom\.creator\]\]"),
        ("creation-tool", r"\[\[tool\.pitloom\.creation-tool\]\]"),
    ],
)
def test_validate_config_moved_key_raises(key: str, new_location: str) -> None:
    """A key that moved to [tool.pitloom]/[tool.pitloom.creation] must raise,
    pointing at its new location, rather than being silently ignored."""
    with pytest.raises(ValueError, match=new_location):
        _validate_config({key: "whatever"})


def test_validate_config_unknown_key_raises() -> None:
    """An unrecognised key must raise rather than being silently ignored."""
    with pytest.raises(ValueError, match="unknown key"):
        _validate_config({"typo-field": "x"})


# ---------------------------------------------------------------------------
# initialize() -- happy path
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# initialize() -- disabled
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# finalize() -- cleanup
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# PEP 770 -- build_data["sbom_files"] registration
# ---------------------------------------------------------------------------


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
        assert staged.name == "sbom.spdx3.json"

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


# ---------------------------------------------------------------------------
# Fragment handling
# ---------------------------------------------------------------------------


def test_hook_with_pitloom_fragments() -> None:
    """Fragments listed under [tool.pitloom] are merged."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path, '[tool.pitloom.fragments]\nfiles = ["frag.json"]\n'
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
            tmp_path, '[tool.pitloom.fragments]\nfiles = ["does_not_exist.json"]\n'
        )

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}

        with caplog.at_level(logging.WARNING):
            hook.initialize("standard", build_data)

        assert any("does_not_exist.json" in msg for msg in caplog.messages)
        # SBOM is still generated despite the missing fragment
        assert hook._sbom_staging_path is not None

        hook.finalize("standard", build_data, "")


# ---------------------------------------------------------------------------
# Integration: sampleproject-hatchling fixture
# ---------------------------------------------------------------------------


def test_hook_with_sampleproject_fixture() -> None:
    """initialize() succeeds on the real 'sampleproject-hatchling' fixture."""
    fixture_dir = (
        Path(__file__).parent / "fixtures" / "projects" / "sampleproject-hatchling"
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


def test_hook_honours_provenance_format_annotation() -> None:
    """The build hook must thread [tool.pitloom.provenance] format/schema
    through to the assembler -- with format = "annotation", the staged SBOM
    carries provenance as Core Annotation elements and the main package's
    comment is not set from provenance."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject_with_pitloom_config(
            tmp_path,
            '[tool.pitloom.provenance]\nformat = "annotation"\n',
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

        hook.finalize("standard", build_data, "")


# ---------------------------------------------------------------------------
# metadata_from_hatchling -- field mapping (lightweight fake objects)
# ---------------------------------------------------------------------------


_FAKE_CORE_DEFAULTS: dict[str, Any] = {
    "description": "",
    "readme_path": "",
    "readme": "",
    "requires_python": "",
    "license": "",
    "license_expression": "",
    "keywords": [],
    "authors_data": {"name": [], "email": []},
    "urls": {},
    "dependencies": [],
}


def _fake_hatch_metadata(
    *,
    name: str = "fakepkg",
    version: str = "1.0.0",
    core: dict[str, Any] | None = None,
) -> SimpleNamespace:
    """Build a lightweight duck-typed stand-in for Hatchling's
    ``hatchling.metadata.core.ProjectMetadata`` (``.core`` + ``.version``).

    *core* overrides individual ``_FAKE_CORE_DEFAULTS`` fields (including
    ``raw_name``, which defaults to *name*), e.g.
    ``_fake_hatch_metadata(core={"license_expression": "MIT"})``.
    """
    merged_core = {"raw_name": name, **_FAKE_CORE_DEFAULTS, **(core or {})}
    return SimpleNamespace(
        name=name, version=version, core=SimpleNamespace(**merged_core)
    )


def test_metadata_from_hatchling_maps_resolved_version() -> None:
    """The resolved (possibly dynamic) version must be used as-is."""
    hatch_meta = _fake_hatch_metadata(version="9.9.9")
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.version == "9.9.9"
    assert metadata.provenance["version"] == (
        "Source: Hatchling build backend | Field: project.version"
    )


def test_metadata_from_hatchling_maps_dependencies() -> None:
    """Resolved dependencies (including dynamic ones) must be carried over."""
    hatch_meta = _fake_hatch_metadata(core={"dependencies": ["requests>=2.0", "click"]})
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.dependencies == ["requests>=2.0", "click"]
    assert metadata.provenance["dependencies"] == (
        "Source: Hatchling build backend | Field: project.dependencies"
    )


def test_metadata_from_hatchling_canonicalises_dependency_markers() -> None:
    """Dependency specifiers are normalised to ``packaging`` canonical form.

    Hatchling exposes markers with source quoting (single quotes); the CLI
    path (``read_pyproject`` via ``pyproject-metadata``) stringifies through
    ``packaging.Requirement`` (double quotes).  Canonicalising here keeps the
    hook and CLI dependency lists -- and thus the deterministic document
    UUID -- identical for the same source tree.
    """
    hatch_meta = _fake_hatch_metadata(
        core={"dependencies": ["tomli>=2.0.0; python_version<'3.11'"]}
    )
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.dependencies == ['tomli>=2.0.0; python_version < "3.11"']


def test_metadata_from_hatchling_matches_read_pyproject_for_uuid() -> None:
    """Hook and CLI paths must yield the same doc UUID for a static project.

    Regression guard: switching the hook to Hatchling's resolved metadata
    must not change the document identity of a project whose metadata is
    fully static (as Pitloom's own is).
    """
    root = Path(__file__).resolve().parent.parent
    cli_meta, _ = read_pyproject(root / "pyproject.toml")
    hatch_pm = hatchling_metadata_core.ProjectMetadata(str(root), PluginManager())
    hook_meta = metadata_from_hatchling(hatch_pm, root)

    assert hook_meta.name == cli_meta.name
    assert hook_meta.version == cli_meta.version
    assert hook_meta.dependencies == cli_meta.dependencies
    assert compute_doc_uuid(
        hook_meta.name, hook_meta.version or "x", hook_meta.dependencies
    ) == compute_doc_uuid(cli_meta.name, cli_meta.version or "x", cli_meta.dependencies)


SYNTHETIC_NONCANONICAL_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "My_Package.Extra"
version = "1.0.0"
dependencies = ["typing_extensions>=4.0", "zope.interface>=5.0"]
"""


def test_metadata_from_hatchling_matches_read_pyproject_for_noncanonical_name() -> None:
    """CLI and hook paths must agree even when the name/deps are non-canonical.

    Regression guard for the gap the earlier, name-only ``raw_name`` fix and
    the marker-only ``_normalize_dependencies`` helper both missed: a project
    name with an uppercase letter, underscore, and dot (``My_Package.Extra``)
    and dependency names with an underscore (``typing_extensions``) and a dot
    (``zope.interface``). Before this fix, Hatchling's own PEP 503
    normalisation made the hook report ``name == "my-package-extra"`` and
    canonicalised dependency names, while the CLI path left both untouched,
    giving the same project two different deterministic document UUIDs
    depending on which path generated the SBOM.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path, SYNTHETIC_NONCANONICAL_PYPROJECT)

        cli_meta, _ = read_pyproject(tmp_path / "pyproject.toml")
        hatch_pm = hatchling_metadata_core.ProjectMetadata(
            str(tmp_path), PluginManager()
        )
        hook_meta = metadata_from_hatchling(hatch_pm, tmp_path)

        assert cli_meta.name == "My_Package.Extra"
        assert hook_meta.name == "My_Package.Extra"
        assert hook_meta.name == cli_meta.name

        expected_deps = ["typing-extensions>=4.0", "zope-interface>=5.0"]
        assert cli_meta.dependencies == expected_deps
        assert hook_meta.dependencies == expected_deps

        assert compute_doc_uuid(
            hook_meta.name, hook_meta.version or "x", hook_meta.dependencies
        ) == compute_doc_uuid(
            cli_meta.name, cli_meta.version or "x", cli_meta.dependencies
        )


def test_metadata_from_hatchling_maps_urls() -> None:
    """Resolved project URLs must be carried over verbatim."""
    hatch_meta = _fake_hatch_metadata(
        core={"urls": {"Homepage": "https://example.com"}}
    )
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.urls == {"Homepage": "https://example.com"}


def test_metadata_from_hatchling_maps_authors() -> None:
    """``authors_data`` (name-only and email entries) must map to
    ``[{name, email?}, ...]``."""
    hatch_meta = _fake_hatch_metadata(
        core={
            "authors_data": {
                "name": ["Bob"],
                "email": ["Alice Smith <alice@example.com>", "carol@example.com"],
            }
        }
    )
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert {"name": "Bob"} in metadata.authors
    assert {"name": "Alice Smith", "email": "alice@example.com"} in metadata.authors
    assert {"email": "carol@example.com"} in metadata.authors
    assert metadata.provenance["authors"] == (
        "Source: Hatchling build backend | Field: project.authors"
    )


def test_metadata_from_hatchling_tolerates_none_authors_data() -> None:
    """``authors_data=None`` must not crash ``metadata_from_hatchling``.

    Every sibling field is defended with ``or []``/``or {}``; a duck-typed
    stand-in (or a future Hatchling release) returning ``None`` for
    ``authors_data`` must degrade to "no authors" rather than raising
    ``AttributeError`` from ``None.get(...)``.
    """
    hatch_meta = _fake_hatch_metadata(core={"authors_data": None})
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert not metadata.authors
    assert "authors" not in metadata.provenance


def test_metadata_from_hatchling_license_expression_used_directly() -> None:
    """A resolved SPDX license expression needs no fallback detection."""
    hatch_meta = _fake_hatch_metadata(core={"license_expression": "Apache-2.0"})
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.license_name == "Apache-2.0"
    assert metadata.provenance["license"] == (
        "Source: Hatchling build backend | Field: project.license"
    )


def test_metadata_from_hatchling_license_fallback_to_project_dir() -> None:
    """When neither ``license`` nor ``license_expression`` is set, fall back
    to :func:`~pitloom.extract._license.detect_license_for_project`."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
        hatch_meta = _fake_hatch_metadata()
        metadata = metadata_from_hatchling(hatch_meta, tmp_path)
        assert metadata.license_name == "MIT"
        assert "LICENSE" in (metadata.provenance.get("license") or "")


MISSING_README_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "testpkg"
version = "0.1.0"
readme = "MISSING.md"
"""

MISSING_LICENSE_FILE_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "testpkg"
version = "0.1.0"
license = {file = "MISSING-LICENSE.txt"}
"""


def test_metadata_from_hatchling_tolerates_missing_readme_file() -> None:
    """A declared readme file that does not exist must not crash the hook.

    Hatchling's ``core.readme`` / ``core.readme_path`` are lazily evaluated
    and raise a bare ``OSError`` (not ``FileNotFoundError``) when the file is
    missing; ``metadata_from_hatchling`` must catch it and degrade to
    ``readme=None`` rather than propagate it, mirroring
    ``read_pyproject()``'s existing tolerance for the same situation.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path, MISSING_README_PYPROJECT)

        hatch_pm = hatchling_metadata_core.ProjectMetadata(
            str(tmp_path), PluginManager()
        )
        metadata = metadata_from_hatchling(hatch_pm, tmp_path)

        assert metadata.readme is None


def test_metadata_from_hatchling_tolerates_missing_license_file() -> None:
    """A declared license *file* that does not exist must not crash the hook.

    Mirrors :func:`test_metadata_from_hatchling_tolerates_missing_readme_file`
    for ``core.license`` / ``core.license_expression``, which raise the same
    bare ``OSError`` for a missing ``project.license.file``.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path, MISSING_LICENSE_FILE_PYPROJECT)

        hatch_pm = hatchling_metadata_core.ProjectMetadata(
            str(tmp_path), PluginManager()
        )
        # Should not raise; falls through to license detection (finds nothing).
        metadata = metadata_from_hatchling(hatch_pm, tmp_path)

        assert metadata.license_name is None


# ---------------------------------------------------------------------------
# [tool.poetry] gap-fill fallback (finding 6)
# ---------------------------------------------------------------------------

POETRY_GAP_FILL_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "testpkg"
version = "0.1.0"
description = "Test package."

[tool.poetry]
name = "testpkg"
version = "0.1.0"
authors = ["Poetry Author <poetry@example.com>"]
keywords = ["from-poetry", "gap-fill"]
"""


def test_metadata_from_hatchling_fills_gaps_from_poetry() -> None:
    """``[tool.poetry]`` fills authors/keywords missing from ``[project]``.

    ``read_pyproject`` (the CLI path) already recovers these fields from
    ``[tool.poetry]`` via ``_try_read_poetry()``/``_merge_with_poetry()``;
    the Hatchling hook path must do the same so a project relying on this
    gap-fill is not silently incomplete when built via the hook.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path, POETRY_GAP_FILL_PYPROJECT)

        hatch_pm = hatchling_metadata_core.ProjectMetadata(
            str(tmp_path), PluginManager()
        )
        metadata = metadata_from_hatchling(hatch_pm, tmp_path)

        # [project] fields are untouched.
        assert metadata.name == "testpkg"
        assert metadata.description == "Test package."
        # Fields absent from [project] are recovered from [tool.poetry].
        assert metadata.authors == [
            {"name": "Poetry Author", "email": "poetry@example.com"}
        ]
        assert metadata.keywords == ["from-poetry", "gap-fill"]


# ---------------------------------------------------------------------------
# Hook uses Hatchling's resolved (dynamic) version
# ---------------------------------------------------------------------------


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
        Path(__file__).parent
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


# ---------------------------------------------------------------------------
# target_name guard -- sdist builds are skipped
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Invalid config raises before any I/O
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Compact / JCS-canonical output enforcement
# ---------------------------------------------------------------------------

PYPROJECT_WITH_PRETTY = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "testpkg"
version = "0.1.0"
description = "Test package."
requires-python = ">=3.10"

[tool.pitloom]
pretty = true
"""


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
