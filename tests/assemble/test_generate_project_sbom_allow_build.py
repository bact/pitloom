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
import shutil
from pathlib import Path
from unittest import mock

import pytest

from pitloom.assemble import generate, generate_project_sbom
from pitloom.core.build_options import BuildOptions
from pitloom.core.project import ProjectFile, ProjectMetadata
from tests.cli.shared import _make_simple_project
from tests.warning_helpers import file_values

_MODEL_NPY = (
    Path(__file__).parent.parent
    / "fixtures"
    / "aimodels"
    / "numpy"
    / "example-model-v1.npy"
)
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


def _stable_scan_run(
    tmp_path: Path, name: str, caplog: pytest.LogCaptureFixture
) -> tuple[Path, str, list[str]]:
    """Run an allow-build generation whose extract dir is ``extract-<name>``."""
    (tmp_path / name).mkdir()
    project_dir = _make_simple_project(tmp_path / name)
    extract = tmp_path / f"extract-{name}"
    pkg = extract / "demo"
    pkg.mkdir(parents=True)
    shutil.copyfile(_MODEL_NPY, pkg / "model.npy")
    (pkg / "bad.onnx").write_bytes(b"corrupt")
    (pkg / "use.py").write_text('np.load("model.npy")\n', encoding="utf-8")
    files = [
        ProjectFile(
            physical_path=str(pkg / fname),
            distribution_path=f"demo/{fname}",
            digest_sha256=str(i) * 64,
        )
        for i, fname in enumerate(["model.npy", "bad.onnx", "use.py"])
    ]
    caplog.clear()
    with mock.patch(
        "pitloom.assemble._generators.get_wheel_files",
        return_value=(None, files, lambda: None),
    ):
        with caplog.at_level(logging.WARNING):
            out = generate_project_sbom(
                project_dir,
                offline=True,
                build_options=BuildOptions(allow=True),
                scan_model_usage=True,
            )
    values = file_values(r.getMessage() for r in caplog.records)
    return extract, out, values


def test_generate_project_sbom_allow_build_model_scan_is_stable(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two allow-build runs with different extract dirs give identical
    SBOM bytes and warnings that never name an extract dir.

    The byte and output assertions are guards; the ``FILE=`` assertion is the
    scanner-path check."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    extract_a, out_a, files_a = _stable_scan_run(tmp_path, "a", caplog)
    extract_b, out_b, files_b = _stable_scan_run(tmp_path, "b", caplog)

    assert extract_a != extract_b
    assert out_a == out_b
    for extract in (extract_a, extract_b):
        assert str(extract) not in out_a
    assert "hasDataFile" in out_a
    assert files_a
    for value in files_a + files_b:
        assert str(extract_a) not in value
        assert str(extract_b) not in value


def test_generate_project_sbom_defers_cleanup_past_ai_model_scan(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``get_wheel_files()``'s cleanup callback (a real removal only for a
    build-and-read result, see ``_models_wheel_build_and_read.py``) must not
    run before ``scan_project_for_ai_models()`` re-reads each returned
    ``ProjectFile``'s bytes from ``physical_path``; otherwise every ``.py``
    file logs a spurious "could not read for usage scanning" WARNING.
    Simulates a build-and-read-sourced file (a real file outside
    *project_dir*, deleted by ``cleanup``) without a real PEP 517 build."""
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
                project_dir,
                offline=True,
                build_options=BuildOptions(allow=True),
                scan_model_usage=True,
            )

    assert cleanup_calls == ["cleanup"]
    assert "could not read for usage scanning" not in caplog.text


@pytest.mark.parametrize(
    "target",
    [
        "pitloom.core.project.ProjectMetadata.replace_with_fresh_containers",
        "pitloom.assemble._generators.scan_project_for_ai_models",
        "pitloom.assemble._generators.run_enrichers_for_models",
    ],
    ids=[
        "fresh_containers",
        "ai_model_scan",
        "enrichment",
    ],
)
def test_generate_project_sbom_cleanup_runs_even_if_step_raises(
    tmp_path: Path, target: str
) -> None:
    """One case per step inside the try/finally block that guards
    ``cleanup_discovery()`` (see ``_generators.py``): a build-and-read temp
    directory must not leak whichever of the three steps between
    ``get_wheel_files()`` returning and the function moving on (the
    fresh-containers copy, AI-model scanning, enrichment) raises. Moving any
    one of them outside the ``try/finally`` fails exactly its own case."""
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
    """Cleanup runs strictly after every step, in order.

    The parametrized test above only proves cleanup is called when a step
    raises; a step moved to run *after* cleanup still calls it once. This test
    records each step's name in one list and asserts the exact order, so
    reordering or hoisting any step across the try/finally boundary is caught
    whether or not that step raises."""
    project_dir = _make_simple_project(tmp_path)
    call_order: list[str] = []

    def _cleanup() -> None:
        call_order.append("cleanup")

    real_fresh_containers = ProjectMetadata.replace_with_fresh_containers

    def _spy_fresh_containers(
        self: ProjectMetadata, **changes: object
    ) -> ProjectMetadata:
        call_order.append("fresh_containers")
        return real_fresh_containers(self, **changes)

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
        mock.patch.object(
            ProjectMetadata,
            "replace_with_fresh_containers",
            autospec=True,
            side_effect=_spy_fresh_containers,
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
        "fresh_containers",
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
