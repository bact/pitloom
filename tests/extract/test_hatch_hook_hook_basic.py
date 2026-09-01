# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Pitloom Hatchling build hook (pitloom.plugins.hatch):
lifecycle basics, staging, and fragments.

See also:
- :mod:`tests.extract.test_hatch_hook_creators` for creators and creation metadata.
- :mod:`tests.extract.test_hatch_hook_hook_integration` for integration tests.
"""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.models import generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

from .conftest import (
    make_hook,
    write_pyproject,
    write_pyproject_with_pitloom_config,
)

pytest.importorskip("hatchling", reason="hatchling is required for hook tests")


def test_hook_initialize_honors_pitloom_debug_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: initialize() calls bare configure_logging() before
    its own work, same as the CLI's `project` subcommand (see
    test_cli_parser.py's test_debug_flag_survives_a_generator_reconfiguring_logging).
    The hook has no --debug flag; PITLOOM_DEBUG is its only lever."""
    # setenv, not delenv: avoids leaking PITLOOM_DEBUG=1 into later tests
    # (see tests/test_logging_config.py for the mechanism).
    monkeypatch.setenv("PITLOOM_DEBUG", "1")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert logging.getLogger("pitloom").getEffectiveLevel() == logging.DEBUG

        hook.finalize("standard", build_data, "")


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


def test_hook_custom_basename_stored() -> None:
    """A custom [tool.pitloom] sbom-basename must be reflected in staged filename."""
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

        hook.finalize("standard", build_data, "")

        assert not staged.exists()
        assert hook._staging_dir is None
        assert hook._sbom_staging_path is None


def test_hook_initialize_cleans_up_staging_dir_on_late_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If something after staging (build_data mutation, the final log
    line) raises, initialize() must clean up the just-created staging
    directory itself -- it cannot rely on finalize() to do it, since
    Hatchling's own hook contract doesn't guarantee finalize() runs after
    a failed initialize()."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}

        cleanup_calls: list[str] = []
        original_cleanup = tempfile.TemporaryDirectory.cleanup

        def _tracking_cleanup(self: Any) -> None:
            cleanup_calls.append(self.name)
            original_cleanup(self)

        monkeypatch.setattr(tempfile.TemporaryDirectory, "cleanup", _tracking_cleanup)
        monkeypatch.setattr(
            "pitloom.plugins.hatch.log.info",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        with pytest.raises(RuntimeError, match="boom"):
            hook.initialize("standard", build_data)

        assert len(cleanup_calls) == 1
        assert not Path(cleanup_calls[0]).exists()
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
        hook.finalize("standard", build_data, "")


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
    """[tool.pitloom] sbom-basename must determine filename appended to sbom_files."""
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
        assert hook._sbom_staging_path is not None

        hook.finalize("standard", build_data, "")
