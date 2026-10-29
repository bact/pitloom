# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Pitloom Hatchling build hook (pitloom.plugins.hatch):
lifecycle basics, staging, and fragments.

See also:
- :mod:`tests.extract.project.test_hatch_hook_creators`
  for creators and creation metadata.
- :mod:`tests.extract.project.test_hatch_hook_hook_integration` for integration tests.
"""

# pylint: disable=protected-access

from __future__ import annotations

import json
import logging
import signal
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from unittest import mock

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.models import generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.messages import LFS_POINTER, CodedValueError, trusted_message
from pitloom.plugins.hatch import PitloomBuildHook

from ..conftest import (
    make_hook,
    staged_sbom,
    write_pyproject,
    write_pyproject_with_pitloom_config,
)


def test_hook_initialize_honors_pitloom_debug_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """initialize() calls bare configure_logging() before its own work, as the
    CLI's `project` subcommand does (see test_cli_parser.py's
    test_debug_flag_survives_a_generator_reconfiguring_logging). The hook has
    no --debug flag; PITLOOM_DEBUG is its only lever."""
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

        staged = staged_sbom(build_data)

        assert staged is not None
        assert staged.exists()
        assert staged.stat().st_size > 0

        hook.finalize("standard", build_data, "")


def test_hook_sbom_is_valid_json() -> None:
    """The staged SBOM must be valid JSON-LD with @context and @graph."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        staged = staged_sbom(build_data)

        assert staged is not None
        data = json.loads(staged.read_text(encoding="utf-8"))
        assert "@context" in data
        assert "@graph" in data

        hook.finalize("standard", build_data, "")


def test_hook_leaves_signal_handling_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hook never builds (it *is* the build), so the termination guard
    that get_wheel_files() enters must never install a signal handler
    inside the host build frontend's process."""
    spy = mock.Mock(wraps=signal.signal)
    monkeypatch.setattr(signal, "signal", spy)
    with tempfile.TemporaryDirectory() as tmp:
        write_pyproject(Path(tmp))
        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)
        staged = staged_sbom(build_data)
        assert staged is not None
        hook.finalize("standard", build_data, "")
    spy.assert_not_called()


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

        staged = staged_sbom(build_data)

        assert staged is not None
        assert staged.name == "custom.spdx3.json"

        hook.finalize("standard", build_data, "")


def test_hook_disabled_skips_generation() -> None:
    """When enabled=false, initialize() must not stage any file."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {"enabled": False})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        assert staged_sbom(build_data) is None
        assert hook._staging_dir is None


def test_hook_finalize_cleans_up() -> None:
    """finalize() must remove the temporary staging directory."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path)

        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        hook.initialize("standard", build_data)

        staged = staged_sbom(build_data)
        assert staged is not None and staged.exists()

        hook.finalize("standard", build_data, "")

        assert not staged.exists()
        assert hook._staging_dir is None


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

        def _raise_when_staged(msg: str, *_args: Any, **_kwargs: Any) -> None:
            if msg.startswith("Pitloom: staged"):
                raise RuntimeError("boom")

        monkeypatch.setattr("pitloom.plugins.hatch.log.info", _raise_when_staged)

        with pytest.raises(RuntimeError, match="boom"):
            hook.initialize("standard", build_data)

        assert len(cleanup_calls) == 1
        assert not Path(cleanup_calls[0]).exists()
        assert hook._staging_dir is None
        staged = staged_sbom(build_data)
        assert staged is not None and not staged.exists()


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

        staged = staged_sbom(build_data)

        assert staged is not None
        data = json.loads(staged.read_text(encoding="utf-8"))
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

        with caplog.at_level(logging.INFO):
            hook.initialize("standard", build_data)

        assert any("does_not_exist.json" in msg for msg in caplog.messages)
        staged = staged_sbom(build_data)
        assert staged is not None
        # The count is of the fragments merged, not of those configured.
        assert [m for m in caplog.messages if "(0 fragment(s))" in m]

        hook.finalize("standard", build_data, "")


def test_hook_editable_variant_is_skipped_with_one_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An editable wheel holds a .pth file, not the project's files: no SBOM."""
    with tempfile.TemporaryDirectory() as tmp:
        write_pyproject(Path(tmp))
        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        with caplog.at_level(logging.INFO):
            hook.initialize("editable", build_data)
        assert staged_sbom(build_data) is None
        assert "sbom_files" not in build_data
        assert [m for m in caplog.messages if "'editable' skipped" in m] != []
        assert len(caplog.messages) == 1


@pytest.mark.parametrize(
    ("configured", "from_hook"),
    [
        ("sub/testpkg-0.1.0.spdx3.json", False),
        ("/tmp/x/testpkg-0.1.0.spdx3.json", True),
        ("sub/TestPkg-0.1.0.SPDX3.json", False),
        ("/tmp/x/TESTPKG-0.1.0.spdx3.json", True),
    ],
    ids=["project-sbom-files", "other-hook", "case-only-project", "case-only-hook"],
)
def test_hook_refuses_an_sbom_name_already_placed(
    caplog: pytest.LogCaptureFixture, configured: str, from_hook: bool
) -> None:
    """Whatever Hatchling already puts under .dist-info/sboms/ under the
    staged name (``sbom-files``, or another hook's ``build_data`` entry) is
    one ERROR, naming ``sbom-basename``, and nothing is staged."""
    with tempfile.TemporaryDirectory() as tmp:
        write_pyproject(Path(tmp))
        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        if from_hook:
            build_data["sbom_files"] = [configured]
        else:
            cast(Any, hook.build_config).sbom_files.append(configured)
        with caplog.at_level(logging.ERROR):
            with pytest.raises(ValueError, match="sbom-basename"):
                hook.initialize("standard", build_data)
        assert build_data.get("sbom_files", []) == ([configured] if from_hook else [])
        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(errors) == 1
        assert errors[0].getMessage().startswith("SBOM generation failed: ")
        assert configured in errors[0].getMessage()


_POINTER_TEXT = (
    "'m.bin': header is a Git LFS pointer, content not pulled "
    f"(oid sha256:{'0f' * 32}, size 3 bytes); run 'git lfs pull'"
)


@pytest.mark.parametrize(
    ("raised", "tail"),
    [
        (
            CodedValueError(LFS_POINTER, path="m.bin", oid="0f" * 32, size=3),
            f"{_POINTER_TEXT} [lfs-pointer]",
        ),
        (ValueError("'m.bin': x"), "'m.bin': x"),
    ],
    ids=["coded", "plain"],
)
def test_hook_failure_line_ends_in_a_catalogued_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raised: ValueError,
    tail: str,
) -> None:
    """The one ``ERROR:`` of a failed build ends in the exception's code, as
    the CLI's does; a plain exception prints as before."""

    def _fail(*_args: object) -> None:
        raise raised

    monkeypatch.setattr(PitloomBuildHook, "_generate", _fail)
    hook = make_hook(str(tmp_path), {})
    with pytest.raises(ValueError):
        hook.initialize("standard", {})
    err = capsys.readouterr().err.splitlines()
    assert err == [f"ERROR: SBOM generation failed: {tail}"]
    assert trusted_message(err[0]) is (LFS_POINTER if tail != "'m.bin': x" else None)
