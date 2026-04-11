# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileType: SOURCE

"""SBOM assemblers for different output specifications."""

from __future__ import annotations

from pathlib import Path

from pitloom.assemble.spdx3.document import build
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.models import get_wheel_files
from pitloom.core.project import ProjectMetadata
from pitloom.extract.pyproject import read_pyproject
from pitloom.extract.scanner import scan_project_for_ai_models


def generate_sbom(
    project_dir: Path,
    output_path: Path | None = None,
    creation_info: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
) -> str:
    """Generate an SPDX 3 SBOM for a Python project.

    Automatically detects the build backend and reads metadata from the
    appropriate source(s):

    * **Hatchling / other PEP 517 backends** — ``pyproject.toml [project]``
    * **Setuptools** — ``pyproject.toml [project]`` (when present), supplemented
      by ``setup.cfg`` and/or ``setup.py``; or ``setup.cfg`` / ``setup.py``
      alone when no ``pyproject.toml`` exists

    Args:
        project_dir: Path to the project directory.
        output_path: If given, the JSON-LD output is also written to this path.
        creation_info: Creator and timestamp metadata for the SBOM document.
            When ``None`` a default :class:`~pitloom.core.creation.CreationMetadata`
            is used (creator ``"Pitloom"``, current UTC time).
        pretty: If ``True``, indent the JSON output with 2 spaces.
            If ``False``, produce compact output (no extra whitespace).
            If ``None`` (default), read the setting from ``[tool.pitloom] pretty``
            (which itself defaults to ``False``).
        describe_relationship: Controls whether relationship descriptions are
            added for human readability.  ``None`` defers to project config.

    Returns:
        JSON-LD string of the generated SPDX 3 SBOM.

    Raises:
        FileNotFoundError: If no project configuration is found in
            ``project_dir`` (no ``pyproject.toml``, ``setup.cfg``, or
            ``setup.py``).
        ValueError: If required project metadata (e.g., ``name``) is missing.
    """
    metadata, pitloom_config = _load_project_metadata(project_dir)
    effective_pretty: bool = pitloom_config.pretty if pretty is None else pretty
    effective_describe: bool = bool(
        pitloom_config.describe_relationship
        if describe_relationship is None
        else describe_relationship
    )

    # Compute Merkle root via hatchling's own file discovery so the UUID
    # matches the build-hook path exactly (same WheelBuilder, same file set).
    merkle_root, project_files = get_wheel_files(project_dir)
    metadata.files = project_files

    ai_models = scan_project_for_ai_models(project_dir, project_files)

    doc = DocumentModel(
        project=metadata,
        creation=creation_info or CreationMetadata(),
        ai_models=ai_models,
    )
    exporter = build(doc, merkle_root=merkle_root)
    merge_fragments(project_dir, pitloom_config.fragments, exporter)

    sbom_json = exporter.to_json(
        pretty=effective_pretty,
        describe_relationship=effective_describe,
    )

    if output_path is not None:
        output_path.write_text(sbom_json, encoding="utf-8")

    return sbom_json


def _load_project_metadata(
    project_dir: Path,
) -> tuple[ProjectMetadata, PitloomConfig]:
    """Load project metadata from available config files.

    Priority order for field values (highest to lowest):

    1. ``pyproject.toml [project]``
    2. ``setup.cfg [metadata]`` / ``[options]``
    3. ``setup.py`` ``setup()`` literal arguments

    When ``pyproject.toml`` is present for a setuptools project, its fields
    take precedence field-by-field; gaps are filled from ``setup.cfg`` /
    ``setup.py`` via :func:`~pitloom.extract.setuptools.merge_metadata`.

    .. note::

        PEP 517 ``prepare_metadata_for_build_wheel`` would give the most
        accurate build-time metadata but requires invoking the build backend
        in a subprocess.  This is planned as a future enhancement.

    Args:
        project_dir: Project root directory.

    Returns:
        A 2-tuple of :class:`~pitloom.core.project.ProjectMetadata` and
        :class:`~pitloom.core.config.PitloomConfig`.

    Raises:
        FileNotFoundError: If no project configuration is found.
        ValueError: If required project metadata is missing.
    """
    # pylint: disable=import-outside-toplevel
    from pitloom.extract.setuptools import (  # pylint: disable=import-outside-toplevel
        detect_build_backend,
        merge_metadata,
        read_setuptools,
    )

    pyproject_path = project_dir / "pyproject.toml"
    has_setuptools_files = (project_dir / "setup.cfg").exists() or (
        project_dir / "setup.py"
    ).exists()

    pyproject_meta: ProjectMetadata | None = None
    pyproject_config: PitloomConfig | None = None

    if pyproject_path.exists():
        try:
            pyproject_meta, pyproject_config = read_pyproject(pyproject_path)
        except ValueError:
            # pyproject.toml exists but has no [project] section
            # (e.g., only [build-system] for a setuptools project).
            pass

    if pyproject_meta is not None:
        assert pyproject_config is not None
        backend = detect_build_backend(project_dir)
        if backend == "setuptools" and has_setuptools_files:
            # Supplement pyproject.toml metadata with setup.cfg / setup.py.
            # pyproject.toml fields win on conflicts (merge_metadata primary).
            try:
                secondary, _ = read_setuptools(project_dir)
                return merge_metadata(pyproject_meta, secondary), pyproject_config
            except Exception:  # pylint: disable=broad-exception-caught
                pass  # pyproject.toml metadata alone is sufficient
        return pyproject_meta, pyproject_config

    if has_setuptools_files:
        return read_setuptools(project_dir)

    # No metadata found — re-raise the most useful error
    if pyproject_path.exists():
        read_pyproject(pyproject_path)  # will raise ValueError

    raise FileNotFoundError(
        f"No project configuration found in {project_dir}. "
        "Expected pyproject.toml, setup.cfg, or setup.py."
    )


__all__ = ["generate_sbom"]
