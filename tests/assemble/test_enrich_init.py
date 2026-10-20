# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.enrich's model-directory resolution
(``run_enrichers_for_models``/``_resolve_model_search_dir``).

See also: :mod:`tests.assemble.test_enrich_readme` for the README
enricher itself, run once the search directory has been resolved.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pitloom.core.ai_metadata import AiModelFormatInfo, AiModelMetadata
from pitloom.core.enrich_config import EnrichConfig
from pitloom.enrich import _resolve_model_search_dir, run_enrichers_for_models

from ..conftest import fake_build_and_read_path


def test_resolve_model_search_dir_relative_physical_path(tmp_path: Path) -> None:
    """The normal case: physical_path is project-relative, so the
    resolved directory is project_dir joined with its parent."""
    format_info = AiModelFormatInfo(physical_path="models/foo.gguf")
    assert _resolve_model_search_dir(tmp_path, format_info) == tmp_path / "models"


def test_resolve_model_search_dir_falls_back_when_physical_path_absolute(
    tmp_path: Path,
) -> None:
    """An absolute physical_path (a build-and-read-sourced file, see
    ProjectFile.physical_path) is not joined onto project_dir with pathlib's
    `/`, which discards project_dir and returns the tempdir path verbatim.
    Falls back to file_path_relative (the wheel-distribution path, always
    project-relative), staying inside project_dir."""
    fake_tempdir = fake_build_and_read_path("pkg", "models", "foo.gguf")
    format_info = AiModelFormatInfo(
        physical_path=fake_tempdir,
        file_path_relative="models/foo.gguf",
    )
    result = _resolve_model_search_dir(tmp_path, format_info)
    assert result == tmp_path / "models"
    assert str(tmp_path) in str(result)
    assert "pitloom-build-and-read" not in str(result)


def test_resolve_model_search_dir_absolute_with_no_relative_fallback(
    tmp_path: Path,
) -> None:
    """When even file_path_relative is unset, the fallback degrades to
    project_dir itself (empty relative path) rather than leaking the
    tempdir -- still wrong information is preferable to a directory
    outside project_dir entirely, but never silently escapes it."""
    format_info = AiModelFormatInfo(
        physical_path=fake_build_and_read_path("some", "tempdir", "foo.gguf")
    )
    result = _resolve_model_search_dir(tmp_path, format_info)
    assert result == tmp_path
    assert "tempdir" not in str(result)


def test_run_enrichers_for_models_uses_resolved_dir(tmp_path: Path) -> None:
    """run_enrichers_for_models must route each model through
    _resolve_model_search_dir rather than joining physical_path
    directly -- proven here by an absolute physical_path (as
    build-and-read would produce) that must not leak into the directory
    passed to run_enrichers."""
    fake_tempdir = fake_build_and_read_path("pkg", "models", "foo.gguf")
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(
            physical_path=fake_tempdir,
            file_path_relative="models/foo.gguf",
        )
    )
    seen_dirs: list[Path] = []

    def _fake_run_enrichers(
        _model: AiModelMetadata, _config: EnrichConfig, model_dir: Path
    ) -> list[object]:
        seen_dirs.append(model_dir)
        return []

    with patch("pitloom.enrich.run_enrichers", side_effect=_fake_run_enrichers):
        run_enrichers_for_models([model], EnrichConfig(local=True), tmp_path)

    assert seen_dirs == [tmp_path / "models"]
