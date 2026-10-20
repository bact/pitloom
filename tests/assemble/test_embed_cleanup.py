# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for when a project-backed embed runs its discovery cleanup: after
every step that reads the discovered files, even when one raises.

See also: :mod:`tests.assemble.test_embed_overrides` (the embed overrides),
tests/assemble/test_generate_project_sbom_allow_build.py (the
same guard for ``generate_project_sbom()``).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom._embed_overlay import merge_file_extras
from pitloom.core.models import merkle_root_of_files
from pitloom.core.project import ProjectFile
from pitloom.embed import ConfigOverrides, embed_wheel_sbom

from .conftest import _make_dummy_wheel


def _make_ctpkg_project_and_wheel(tmp_path: Path) -> Path:
    """Shared fixture setup for the cleanup-timing tests below: a
    minimal Hatchling project (``ctpkg``) plus its built wheel. Returns
    the wheel path."""
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "ctpkg"
version = "1.0.0"

[tool.hatch.build.targets.wheel]
packages = ["ctpkg"]
""",
        encoding="utf-8",
    )
    pkg_dir = tmp_path / "ctpkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    return _make_dummy_wheel(tmp_path / "dist", "ctpkg", "1.0.0")


def test_embed_wheel_defers_cleanup_past_ai_model_scan(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``embed.py``'s ``_build_sbom_from_project_and_wheel`` has the same
    cleanup-timing hazard as ``generate_project_sbom()`` (see the sibling
    test in ``test_generate_project_sbom_allow_build.py``):
    ``scan_project_for_ai_models()`` runs after ``get_wheel_files()`` and
    must still see a build-and-read-sourced file's bytes before the cleanup
    callback removes them."""
    wheel_path = _make_ctpkg_project_and_wheel(tmp_path)

    fake_extract_dir = tmp_path / "fake-extract"
    fake_extract_dir.mkdir()
    py_file = fake_extract_dir / "mod.py"
    py_file.write_text("x = 1\n", encoding="utf-8")
    project_file = ProjectFile(
        physical_path=str(py_file),
        distribution_path="ctpkg/mod.py",
    )
    cleanup_calls: list[str] = []

    def _cleanup() -> None:
        cleanup_calls.append("cleanup")
        py_file.unlink()

    monkeypatch.setattr(
        "pitloom._embed_build_sbom.get_wheel_files",
        lambda *a, **k: (None, [project_file], _cleanup),
    )
    with caplog.at_level(logging.WARNING):
        embed_wheel_sbom(
            wheel_path,
            project_dir=tmp_path,
            overrides=ConfigOverrides(scan_model_usage=True),
        )

    assert cleanup_calls == ["cleanup"]
    assert "could not read for usage scanning" not in caplog.text


@pytest.mark.parametrize(
    "target",
    [
        "pitloom._embed_build_sbom._merge_file_extras",
        "pitloom.core.project.ProjectMetadata.replace_with_fresh_containers",
        "pitloom._embed_build_sbom.merkle_root_of_files",
        "pitloom._embed_build_sbom.scan_project_for_ai_models",
        "pitloom._embed_build_sbom.run_enrichers_for_models",
    ],
    ids=[
        "merge_file_extras",
        "fresh_containers",
        "compute_merkle_root",
        "ai_model_scan",
        "enrichment",
    ],
)
def test_embed_wheel_cleanup_runs_even_if_step_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    """One case per step inside the ``EmbedFileCache`` block
    of ``_build_sbom_from_project_and_wheel()`` (``_embed_build_sbom.py``),
    whose exit runs the discovery cleanup: a build-and-read temp
    directory must not leak whichever of the five steps after
    ``get_wheel_files()`` returns (the file-extras merge, the
    fresh-containers copy, Merkle-root recomputation, AI-model
    scanning, enrichment) raises. Moving any one of them out of the
    block must fail exactly its own parametrize case."""
    wheel_path = _make_ctpkg_project_and_wheel(tmp_path)

    cleanup_calls: list[str] = []

    def _cleanup() -> None:
        cleanup_calls.append("cleanup")

    monkeypatch.setattr(
        "pitloom._embed_build_sbom.get_wheel_files",
        lambda *a, **k: (None, [], _cleanup),
    )

    def _raise(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr(target, _raise)
    with pytest.raises(RuntimeError, match="boom"):
        embed_wheel_sbom(wheel_path, project_dir=tmp_path)

    assert cleanup_calls == ["cleanup"]


def test_embed_wheel_cleanup_runs_strictly_last_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cleanup runs strictly after every step, in order.

    The parametrized test above only proves cleanup is called when a step
    raises; a step moved to run *after* cleanup still calls it once. This test
    records each step's name in one list and asserts the exact order, so
    reordering or hoisting any step out of the ``EmbedFileCache`` block is
    caught whether or not that step raises."""
    wheel_path = _make_ctpkg_project_and_wheel(tmp_path)

    call_order: list[str] = []

    def _cleanup() -> None:
        call_order.append("cleanup")

    monkeypatch.setattr(
        "pitloom._embed_build_sbom.get_wheel_files",
        lambda *a, **k: (None, [], _cleanup),
    )

    real_merge_file_extras = merge_file_extras

    def _fake_merge(*args: object, **kwargs: object) -> object:
        call_order.append("merge_file_extras")
        return real_merge_file_extras(*args, **kwargs)  # type: ignore[arg-type]

    real_compute_merkle = merkle_root_of_files

    def _fake_merkle(*args: object, **kwargs: object) -> object:
        call_order.append("compute_merkle_root")
        return real_compute_merkle(*args, **kwargs)  # type: ignore[arg-type]

    def _fake_scan(*_args: object, **_kwargs: object) -> list[object]:
        call_order.append("ai_model_scan")
        return []

    def _fake_enrich(*_args: object, **_kwargs: object) -> list[object]:
        call_order.append("enrichment")
        return []

    monkeypatch.setattr("pitloom._embed_build_sbom._merge_file_extras", _fake_merge)
    monkeypatch.setattr("pitloom._embed_build_sbom.merkle_root_of_files", _fake_merkle)
    monkeypatch.setattr(
        "pitloom._embed_build_sbom.scan_project_for_ai_models", _fake_scan
    )
    monkeypatch.setattr(
        "pitloom._embed_build_sbom.run_enrichers_for_models", _fake_enrich
    )

    embed_wheel_sbom(wheel_path, project_dir=tmp_path)

    assert call_order == [
        "merge_file_extras",
        "compute_merkle_root",
        "ai_model_scan",
        "enrichment",
        "cleanup",
    ]
