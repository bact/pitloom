# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Single entry point for resolving a project's metadata and Pitloom config.

Tries ``pyproject.toml`` first, then ``setup.cfg``/``setup.py``, or reads an
sdist archive (.tar.gz, .zip), so both the CLI (:mod:`pitloom.__main__`) and
the library entry point (:func:`pitloom.assemble.generate_project_sbom`) resolve
project metadata the same way.
"""

from __future__ import annotations

from pathlib import Path

from pitloom.core.config import PitloomConfig
from pitloom.core.project import ProjectMetadata
from pitloom.extract._pyproject import read_pyproject
from pitloom.extract._sdist import read_sdist
from pitloom.extract._setuptools import read_setuptools

_SDIST_EXTENSIONS = (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".zip")


def _is_sdist_archive(path: Path) -> bool:
    """Return True if path points to an sdist file archive."""
    if not path.is_file():
        return False
    name_lower = path.name.lower()
    return any(name_lower.endswith(ext) for ext in _SDIST_EXTENSIONS)


def read_project(
    project_path: Path,
) -> tuple[ProjectMetadata, PitloomConfig, Path | None]:
    """Resolve project metadata and Pitloom config from *project_path*.

    If *project_path* is a source distribution archive (.tar.gz, .zip),
    extracts metadata from its internal PKG-INFO or pyproject.toml.
    Otherwise, treats *project_path* as a directory and tries
    ``pyproject.toml`` first, then ``setup.cfg``/``setup.py``.

    Args:
        project_path: Project root directory or sdist archive path.

    Returns:
        A 3-tuple of:

        * :class:`~pitloom.core.project.ProjectMetadata` -- resolved project
          metadata.
        * :class:`~pitloom.core.config.PitloomConfig` -- resolved
          ``[tool.pitloom]`` settings.
        * The config file path used (or the archive path itself).

    Raises:
        FileNotFoundError: If *project_path* does not exist or no valid project
            config is found.
        ValueError: If config is malformed.
    """
    if not project_path.exists():
        raise FileNotFoundError(f"Project path not found: {project_path}")

    if _is_sdist_archive(project_path):
        metadata, files = read_sdist(project_path)
        metadata.files = files
        return metadata, PitloomConfig(), project_path

    pyproject_path = project_path / "pyproject.toml"
    if pyproject_path.exists():
        metadata, pitloom_config = read_pyproject(pyproject_path)
        return metadata, pitloom_config, pyproject_path

    setup_cfg = project_path / "setup.cfg"
    setup_py = project_path / "setup.py"
    if setup_cfg.exists() or setup_py.exists():
        metadata, pitloom_config = read_setuptools(project_path)
        config_path = setup_cfg if setup_cfg.exists() else setup_py
        return metadata, pitloom_config, config_path

    raise FileNotFoundError(
        f"No pyproject.toml, setup.cfg, or setup.py found in {project_path}"
    )


__all__ = ["read_project"]
