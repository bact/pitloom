# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Single entry point for resolving a project's metadata and Pitloom config.

Tries ``pyproject.toml`` first, then ``setup.cfg``/``setup.py``, so both the
CLI (:mod:`pitloom.__main__`) and the library entry point
(:func:`pitloom.assemble.generate_sbom`) resolve project metadata and
``[tool.pitloom]`` config the same way, from a single parse.
"""

from __future__ import annotations

from pathlib import Path

from pitloom.core.config import PitloomConfig
from pitloom.core.project import ProjectMetadata
from pitloom.extract.pyproject import read_pyproject
from pitloom.extract.setuptools import read_setuptools


def read_project(
    project_dir: Path,
) -> tuple[ProjectMetadata, PitloomConfig, Path | None]:
    """Resolve project metadata and Pitloom config from *project_dir*.

    Tries ``pyproject.toml`` first (if it exists at all, regardless of
    whether it has a ``[project]`` section), then falls back to
    ``setup.cfg``/``setup.py``. A parse or validation error from either
    source propagates -- it is a genuine config mistake, not a signal to
    silently try the next source.

    Args:
        project_dir: Project root directory.

    Returns:
        A 3-tuple of:

        * :class:`~pitloom.core.project.ProjectMetadata` -- resolved project
          metadata.
        * :class:`~pitloom.core.config.PitloomConfig` -- resolved
          ``[tool.pitloom]`` settings.
        * The config file path used (``pyproject.toml``, ``setup.cfg``, or
          ``setup.py``).

    Raises:
        FileNotFoundError: If none of ``pyproject.toml``, ``setup.cfg``, or
            ``setup.py`` exist in *project_dir*.
        ValueError: If ``[tool.pitloom]`` (or ``[tool:pitloom]``) config is
            malformed.
    """
    pyproject_path = project_dir / "pyproject.toml"
    if pyproject_path.exists():
        metadata, pitloom_config = read_pyproject(pyproject_path)
        return metadata, pitloom_config, pyproject_path

    setup_cfg = project_dir / "setup.cfg"
    setup_py = project_dir / "setup.py"
    if setup_cfg.exists() or setup_py.exists():
        metadata, pitloom_config = read_setuptools(project_dir)
        config_path = setup_cfg if setup_cfg.exists() else setup_py
        return metadata, pitloom_config, config_path

    raise FileNotFoundError(
        f"No pyproject.toml, setup.cfg, or setup.py found in {project_dir}"
    )


__all__ = ["read_project"]
