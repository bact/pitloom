# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests that ``build_options`` reaches ``get_wheel_files()`` unchanged
from every library-API entry point that accepts it
(:func:`pitloom.assemble.generate_project_sbom`,
:func:`pitloom.assemble.generate`), and that a build-and-read cleanup
callback runs only after every step that re-reads file bytes.
``build_options`` has no ``[tool.pitloom]`` cascade, so there is no
config-precedence case to test here, unlike ``use_lockfile``'s sibling
test module.

See also: :mod:`tests.test_build_flag_warnings` for the "build flag has
no effect" warnings on every surface and target kind.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest import mock

import pytest

from pitloom.assemble import generate, generate_project_sbom
from pitloom.core.build_options import BuildOptions
from pitloom.core.project import ProjectFile
from tests.cli.shared import _make_simple_project

_ALL_FLAGS = BuildOptions(allow=True, no_isolation=True, timeout=1234)


def test_generate_project_sbom_threads_build_options(tmp_path: Path) -> None:
    project_dir = _make_simple_project(tmp_path)

    with mock.patch(
        "pitloom.assemble._generators.get_wheel_files",
        autospec=True,
        return_value=(None, [], lambda: None),
    ) as mocked:
        generate_project_sbom(project_dir, offline=True, build_options=_ALL_FLAGS)

    assert mocked.call_args.kwargs["build_options"] is _ALL_FLAGS


def test_generate_project_sbom_defers_cleanup_past_ai_model_scan(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: ``get_wheel_files()``'s cleanup callback (a real
    filesystem removal only for a build-and-read result, see
    ``_models_wheel_build_and_read.py``) must not run before
    ``scan_project_for_ai_models()`` re-reads each returned
    ``ProjectFile``'s bytes from ``physical_path`` -- calling it too
    early turns every ``.py`` file into a spurious "could not read for
    usage scanning" WARNING instead of a clean scan. Caught by manually
    running ``--allow-build`` against a real vendored ``uv_build``
    fixture, where every one of its ~90 Python files logged this
    warning. Simulates a build-and-read-sourced file here (a real file
    physically outside *project_dir*, deleted by ``cleanup``) without
    needing a real PEP 517 build."""
    project_dir = _make_simple_project(tmp_path)
    fake_extract_dir = tmp_path / "fake-extract"
    fake_extract_dir.mkdir()
    py_file = fake_extract_dir / "mod.py"
    py_file.write_text("x = 1\n", encoding="utf-8")

    project_file = ProjectFile(
        physical_path=str(py_file),
        distribution_path="demo/mod.py",
        digest_sha256="e" * 64,
    )
    cleanup_calls: list[str] = []

    def _cleanup() -> None:
        cleanup_calls.append("cleanup")
        py_file.unlink()

    with mock.patch(
        "pitloom.assemble._generators.get_wheel_files",
        return_value=(None, [project_file], _cleanup),
    ):
        with caplog.at_level(logging.WARNING):
            generate_project_sbom(
                project_dir, offline=True, build_options=BuildOptions(allow=True)
            )

    assert cleanup_calls == ["cleanup"]
    assert "could not read for usage scanning" not in caplog.text


@pytest.mark.parametrize(
    "target",
    [
        "pitloom.assemble._generators.resolve_license_file_entries",
        "pitloom.core.project.ProjectMetadata.replace_with_fresh_containers",
        "pitloom.assemble._generators.scan_project_for_ai_models",
        "pitloom.assemble._generators.run_enrichers_for_models",
    ],
    ids=[
        "license_resolution",
        "fresh_containers",
        "ai_model_scan",
        "enrichment",
    ],
)
def test_generate_project_sbom_cleanup_runs_even_if_step_raises(
    tmp_path: Path, target: str
) -> None:
    """Regression, one case per step inside the try/finally block that
    guards ``cleanup_discovery()`` (see ``_generators.py``'s own comment
    on that block): a build-and-read temp directory must not leak
    regardless of WHICH of the four steps between ``get_wheel_files()``
    returning and the function moving on (license-file resolution, the
    fresh-containers copy, AI-model scanning, enrichment) raises --
    every one of them used to run *outside* the ``try/finally`` before
    this was fixed, and a future refactor that moves any single one of
    them back outside it must fail exactly this one parametrize case,
    not silently pass the other three."""
    project_dir = _make_simple_project(tmp_path)
    cleanup_calls: list[str] = []

    def _cleanup() -> None:
        cleanup_calls.append("cleanup")

    with mock.patch(
        "pitloom.assemble._generators.get_wheel_files",
        return_value=(None, [], _cleanup),
    ):
        with mock.patch(target, side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                generate_project_sbom(
                    project_dir, offline=True, build_options=BuildOptions(allow=True)
                )

    assert cleanup_calls == ["cleanup"]


def test_generate_project_sbom_cleanup_runs_strictly_last_in_order(
    tmp_path: Path,
) -> None:
    """Order-sensitivity guard, stronger than the parametrized
    exception-based test above: that test only proves cleanup is called
    at all when a step raises, which does NOT catch a step being moved
    to run *after* cleanup instead of before it -- cleanup would still
    end up called exactly once either way, so a call-count assertion
    passes even for a real ordering regression (confirmed: temporarily
    moving ``run_enrichers_for_models()`` to run after
    ``cleanup_discovery()`` left every case of that parametrized test
    green). This test instead records every step's own name into one
    shared list and asserts the exact order, so a future refactor that
    reorders or hoists any single step across the try/finally boundary
    is caught precisely, regardless of whether that step happens to
    raise."""
    project_dir = _make_simple_project(tmp_path)
    call_order: list[str] = []

    def _cleanup() -> None:
        call_order.append("cleanup")

    def _fake_license_resolution(*_args: object, **_kwargs: object) -> list[object]:
        call_order.append("license_resolution")
        return []

    def _fake_scan(*_args: object, **_kwargs: object) -> list[object]:
        call_order.append("ai_model_scan")
        return []

    def _fake_enrich(*_args: object, **_kwargs: object) -> list[object]:
        call_order.append("enrichment")
        return []

    with (
        mock.patch(
            "pitloom.assemble._generators.get_wheel_files",
            return_value=(None, [], _cleanup),
        ),
        mock.patch(
            "pitloom.assemble._generators.resolve_license_file_entries",
            side_effect=_fake_license_resolution,
        ),
        mock.patch(
            "pitloom.assemble._generators.scan_project_for_ai_models",
            side_effect=_fake_scan,
        ),
        mock.patch(
            "pitloom.assemble._generators.run_enrichers_for_models",
            side_effect=_fake_enrich,
        ),
    ):
        generate_project_sbom(
            project_dir, offline=True, build_options=BuildOptions(allow=True)
        )

    assert call_order == [
        "license_resolution",
        "ai_model_scan",
        "enrichment",
        "cleanup",
    ]


def test_generate_project_sbom_defaults_to_no_build_options(tmp_path: Path) -> None:
    project_dir = _make_simple_project(tmp_path)

    with mock.patch(
        "pitloom.assemble._generators.get_wheel_files",
        autospec=True,
        return_value=(None, [], lambda: None),
    ) as mocked:
        generate_project_sbom(project_dir, offline=True)

    assert mocked.call_args.kwargs["build_options"] == BuildOptions()


def test_generate_dispatches_build_options_to_project_sbom(tmp_path: Path) -> None:
    """``generate()``'s own "project" classification branch must forward
    ``build_options`` unchanged to :func:`generate_project_sbom`."""
    project_dir = _make_simple_project(tmp_path)

    with mock.patch(
        "pitloom.assemble.generate_project_sbom", return_value="{}"
    ) as mocked:
        generate(project_dir, offline=True, build_options=_ALL_FLAGS)

    assert mocked.call_args.kwargs["build_options"] is _ALL_FLAGS
