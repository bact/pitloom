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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

# Skip the entire module if hatchling is not installed.
pytest.importorskip("hatchling", reason="hatchling is required for hook tests")

# Imports below require hatchling (guarded by importorskip above).
# pylint: disable=wrong-import-position
from spdx_python_model import v3_0_1 as spdx3  # noqa: E402

from pitloom.core.models import generate_spdx_id  # noqa: E402
from pitloom.export.spdx3_json import Spdx3JsonExporter  # noqa: E402
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


# pylint: disable=too-few-public-methods
class _StubBuildConfig:
    """Minimal stub of ``BuilderConfig`` for tests that bypass
    ``BuildHookInterface.__init__``.

    Only ``packages`` is needed: ``initialize()`` reads it to discover wheel
    source directories for the Merkle-root computation.  An empty list means
    no source dirs are scanned and ``merkle_root`` is ``None``, which is the
    correct behaviour for ephemeral temp-dir fixtures that contain no package
    source tree.
    """

    packages: list[str] = []


def make_hook(root: str, config: dict[str, Any]) -> PitloomBuildHook:
    """Construct a ``PitloomBuildHook`` without invoking
    ``BuildHookInterface.__init__``.

    ``BuildHookInterface`` stores ``root``, ``config``, and ``build_config``
    under mangled names and exposes them as read-only properties, so we set
    the mangled attributes directly via ``object.__setattr__``.
    """
    hook: PitloomBuildHook = object.__new__(PitloomBuildHook)
    object.__setattr__(hook, "_BuildHookInterface__root", root)
    object.__setattr__(hook, "_BuildHookInterface__config", config)
    object.__setattr__(hook, "_BuildHookInterface__build_config", _StubBuildConfig())
    hook._staging_dir = None
    hook._sbom_staging_path = None
    hook._sbom_filename = "sbom.spdx3.json"
    return hook


def write_pyproject(directory: Path, content: str = MINIMAL_PYPROJECT) -> None:
    """Write ``content`` as ``pyproject.toml`` in ``directory``."""
    (directory / "pyproject.toml").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def test_validate_config_defaults_pass() -> None:
    """Empty config (all defaults) must not raise."""
    _validate_config({})


def test_validate_config_valid_values_pass() -> None:
    """Fully specified valid config must not raise."""
    _validate_config(
        {
            "enabled": True,
            "sbom-basename": "my-sbom",
            "creator-name": "Alice",
            "creator-email": "alice@example.com",
            "fragments": ["a.json", "b.json"],
        }
    )


@pytest.mark.parametrize(
    ("field", "bad_value", "match"),
    [
        ("enabled", "yes", "'enabled' must be a boolean"),
        ("enabled", 1, "'enabled' must be a boolean"),
        ("sbom-basename", 123, "'sbom-basename' must be a string"),
        ("creator-name", 42, "'creator-name' must be a string"),
        ("creator-email", [], "'creator-email' must be a string"),
        ("fragments", "oops", "'fragments' must be a list of strings"),
        ("fragments", [1, 2], "'fragments' must be a list of strings"),
    ],
)
def test_validate_config_invalid_raises(field: str, bad_value: Any, match: str) -> None:
    """Invalid field type or value must raise ``ValueError`` with a clear message."""
    with pytest.raises(ValueError, match=match):
        _validate_config({field: bad_value})


# ---------------------------------------------------------------------------
# initialize() — happy path
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
    """creator-name from hook config must appear in the SBOM graph."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {"creator-name": "Test Creator"})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_staging_path is not None
        data = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))
        graph = data["@graph"]
        names = [e.get("name") for e in graph if e.get("type") == "Person"]
        assert "Test Creator" in names

        hook.finalize("standard", build_data, "")


def test_hook_custom_basename_stored() -> None:
    """A custom sbom-basename in config must be reflected in the staged filename."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {"sbom-basename": "custom"})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert hook._sbom_filename == "custom.spdx3.json"
        assert hook._sbom_staging_path is not None
        assert hook._sbom_staging_path.name == "custom.spdx3.json"

        hook.finalize("standard", build_data, "")


# ---------------------------------------------------------------------------
# initialize() — disabled
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
# finalize() — cleanup
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
# PEP 770 — build_data["sbom_files"] registration
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
    """sbom-basename config must determine the filename appended to sbom_files."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {"sbom-basename": "custom"})
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
    """Fragments listed under [tool.hatch.build.hooks.pitloom] are merged."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

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
        ci.createdBy = [person.spdxId]
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

        hook = make_hook(tmp, {"fragments": ["frag.json"]})
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
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {"fragments": ["does_not_exist.json"]})
        build_data: dict[str, Any] = {}

        with caplog.at_level(logging.WARNING):
            hook.initialize("standard", build_data)

        assert any("does_not_exist.json" in msg for msg in caplog.messages)
        # SBOM is still generated despite the missing fragment
        assert hook._sbom_staging_path is not None

        hook.finalize("standard", build_data, "")


# ---------------------------------------------------------------------------
# Integration: sampleproject fixture
# ---------------------------------------------------------------------------


def test_hook_with_sampleproject_fixture() -> None:
    """initialize() succeeds on the real sampleproject fixture."""
    fixture_dir = Path(__file__).parent / "fixtures" / "sampleproject"
    if not fixture_dir.exists():
        pytest.skip("sampleproject fixture not found")

    hook = make_hook(str(fixture_dir), {"creator-name": "Pitloom CI"})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)

    assert hook._sbom_staging_path is not None
    data = json.loads(hook._sbom_staging_path.read_text(encoding="utf-8"))
    graph = data["@graph"]
    pkg_names = [e.get("name") for e in graph if e.get("type") == "software_Package"]
    assert "sampleproject" in pkg_names

    hook.finalize("standard", build_data, "")


# ---------------------------------------------------------------------------
# Invalid config raises before any I/O
# ---------------------------------------------------------------------------


def test_hook_invalid_config_raises_before_io() -> None:
    """initialize() raises ValueError on bad config without touching the filesystem."""
    # No pyproject.toml written — error must occur before reading it
    with tempfile.TemporaryDirectory() as tmp:
        hook = make_hook(tmp, {"enabled": "yes"})
        build_data: dict[str, Any] = {}
        with pytest.raises(ValueError, match="'enabled' must be a boolean"):
            hook.initialize("standard", build_data)

        assert hook._staging_dir is None
        assert hook._sbom_staging_path is None
