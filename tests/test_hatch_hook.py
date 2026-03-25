# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Loom Hatchling build hook (loom.plugins.hatch)."""

# Tests necessarily access private attributes of LoomBuildHook to inspect
# internal state (white-box testing) and to bypass BuildHookInterface.__init__.
# pylint: disable=protected-access

from __future__ import annotations

import base64
import hashlib
import json
import logging
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

# Skip the entire module if hatchling is not installed.
pytest.importorskip("hatchling", reason="hatchling is required for hook tests")

# Imports below require hatchling (guarded by importorskip above).
# pylint: disable=wrong-import-position
from spdx_python_model import v3_0_1 as spdx3  # noqa: E402

from loom.core.models import generate_spdx_id  # noqa: E402
from loom.export.spdx3_json import Spdx3JsonExporter  # noqa: E402
from loom.plugins.hatch import (  # noqa: E402
    LoomBuildHook,
    _inject_sbom_into_wheel,
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

MINIMAL_WHEEL_RECORD = (
    "testpkg-0.1.0.dist-info/WHEEL,sha256=abc,10\r\n"
    "testpkg-0.1.0.dist-info/RECORD,,\r\n"
)


def make_hook(root: str, config: dict[str, Any]) -> LoomBuildHook:
    """Construct a ``LoomBuildHook`` without invoking ``BuildHookInterface.__init__``.

    ``root`` and ``config`` are stored under mangled names by ``BuildHookInterface``
    and exposed as read-only properties, so we set the mangled attributes directly.
    """
    hook: LoomBuildHook = object.__new__(LoomBuildHook)
    # BuildHookInterface stores root/config as __root / __config (name-mangled).
    # Use object.__setattr__ so the mangled name is passed as a string and
    # static name-style checkers (pylint C0103) do not flag the assignment.
    object.__setattr__(hook, "_BuildHookInterface__root", root)
    object.__setattr__(hook, "_BuildHookInterface__config", config)
    hook._staging_dir = None
    hook._sbom_staging_path = None
    hook._sbom_filename = "sbom.spdx3.json"
    return hook


def write_pyproject(directory: Path, content: str = MINIMAL_PYPROJECT) -> None:
    """Write ``content`` as ``pyproject.toml`` in ``directory``."""
    (directory / "pyproject.toml").write_text(content, encoding="utf-8")


def make_minimal_wheel(path: Path, dist_info: str = "testpkg-0.1.0.dist-info") -> None:
    """Write a minimal valid wheel zip for injection tests."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{dist_info}/WHEEL", "Wheel-Version: 1.0\n")
        zf.writestr(f"{dist_info}/RECORD", MINIMAL_WHEEL_RECORD)


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
            "filename": "sbom.spdx3.json",
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
        ("filename", 123, "'filename' must be a string"),
        ("filename", "", "'filename' must not be empty"),
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


def test_hook_custom_filename_stored() -> None:
    """A custom filename in config must be stored on the hook instance."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {"filename": "custom.spdx3.json"})
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
# PEP 770 wheel injection
# ---------------------------------------------------------------------------


def test_inject_sbom_into_wheel() -> None:
    """_inject_sbom_into_wheel must place the SBOM at the PEP 770 path."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        wheel_path = tmp_path / "testpkg-0.1.0-py3-none-any.whl"
        make_minimal_wheel(wheel_path)

        sbom_content = b'{"@context": "...", "@graph": []}'
        sbom_path = tmp_path / "sbom.spdx3.json"
        sbom_path.write_bytes(sbom_content)

        _inject_sbom_into_wheel(wheel_path, sbom_path, "sbom.spdx3.json")

        with zipfile.ZipFile(wheel_path, "r") as zf:
            names = zf.namelist()
            sbom_entry = "testpkg-0.1.0.dist-info/sboms/sbom.spdx3.json"
            assert sbom_entry in names, f"Expected {sbom_entry!r} in {names}"
            assert zf.read(sbom_entry) == sbom_content


def test_inject_sbom_record_updated() -> None:
    """After injection, RECORD must contain the SBOM hash entry."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        wheel_path = tmp_path / "testpkg-0.1.0-py3-none-any.whl"
        make_minimal_wheel(wheel_path)

        sbom_content = b'{"@graph": []}'
        sbom_path = tmp_path / "sbom.spdx3.json"
        sbom_path.write_bytes(sbom_content)

        _inject_sbom_into_wheel(wheel_path, sbom_path, "sbom.spdx3.json")

        expected_hash = (
            base64.urlsafe_b64encode(hashlib.sha256(sbom_content).digest())
            .rstrip(b"=")
            .decode()
        )
        expected_size = len(sbom_content)

        with zipfile.ZipFile(wheel_path, "r") as zf:
            record = zf.read("testpkg-0.1.0.dist-info/RECORD").decode("utf-8")

        assert f"sha256={expected_hash}" in record
        assert str(expected_size) in record
        assert "testpkg-0.1.0.dist-info/sboms/sbom.spdx3.json" in record


def test_pep770_path_format() -> None:
    """finalize() must inject the SBOM at sboms/<filename> in .dist-info."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        wheel_path = tmp_path / "testpkg-0.1.0-py3-none-any.whl"
        make_minimal_wheel(wheel_path)

        hook = make_hook(tmp, {"filename": "custom.spdx3.json"})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)
        hook.finalize("standard", build_data, str(wheel_path))

        with zipfile.ZipFile(wheel_path, "r") as zf:
            sbom_entry = next(
                (n for n in zf.namelist() if "sboms/custom.spdx3.json" in n),
                None,
            )
        assert sbom_entry is not None, "Expected sboms/custom.spdx3.json in wheel"


def test_hook_finalize_skips_non_wheel() -> None:
    """finalize() must not attempt injection for sdist (.tar.gz) artifacts."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        staged = hook._sbom_staging_path
        assert staged is not None

        # Pass a .tar.gz path — should not raise even though it doesn't exist
        hook.finalize("standard", build_data, str(tmp_path / "testpkg-0.1.0.tar.gz"))

        # Staging dir still cleaned up
        assert hook._staging_dir is None


# ---------------------------------------------------------------------------
# Fragment handling
# ---------------------------------------------------------------------------


def test_hook_with_loom_fragments() -> None:
    """Fragments listed under [tool.hatch.build.hooks.loom] are merged."""
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

    hook = make_hook(str(fixture_dir), {"creator-name": "Loom CI"})
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
