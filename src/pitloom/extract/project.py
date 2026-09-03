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

import logging
from pathlib import Path

from pitloom.core.config import PitloomConfig
from pitloom.core.project import ProjectMetadata
from pitloom.extract._pyproject import read_pyproject
from pitloom.extract._sdist import read_sdist
from pitloom.extract._setuptools import read_setuptools

log = logging.getLogger(__name__)

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

    setup_cfg = project_path / "setup.cfg"
    setup_py = project_path / "setup.py"

    pyproject_path = project_path / "pyproject.toml"
    if pyproject_path.exists():
        metadata, pitloom_config = read_pyproject(pyproject_path)
        if not metadata.name and (setup_cfg.exists() or setup_py.exists()):
            # pyproject.toml exists but resolved no usable metadata --
            # no [project] table (e.g. a custom/legacy build backend
            # declaring only [build-system]) and no [tool.poetry]
            # fallback either -- while setup.cfg/setup.py hold the
            # project's real metadata. Prefer that over the otherwise
            # nameless/versionless stub read_pyproject() returns; the
            # same shape _models_wheel.py's file-discovery dispatch
            # already treats as "no static pyproject.toml config" (see
            # has_resolvable_pyproject_config()).
            log.warning(
                "%s has no usable [project] table and no [tool.poetry] "
                "fallback -- falling back to setup.cfg/setup.py metadata "
                "instead of an empty pyproject.toml-only result",
                pyproject_path,
            )
            metadata, setuptools_pitloom_config = read_setuptools(project_path)
            # [tool.pitloom] always lives in pyproject.toml, never
            # setup.cfg/setup.py -- keep the one read_pyproject() already
            # resolved from the real pyproject.toml unless it's untouched
            # defaults, in which case fall back to whatever read_setuptools()
            # found (its own setup.cfg-based [tool:pitloom] parsing, if any).
            # Never silently drop a real [tool.pitloom] section just because
            # metadata itself had to come from setup.cfg/setup.py instead.
            if pitloom_config == PitloomConfig():
                pitloom_config = setuptools_pitloom_config
            config_path = setup_cfg if setup_cfg.exists() else setup_py
            return metadata, pitloom_config, config_path
        return metadata, pitloom_config, pyproject_path

    if setup_cfg.exists() or setup_py.exists():
        metadata, pitloom_config = read_setuptools(project_path)
        config_path = setup_cfg if setup_cfg.exists() else setup_py
        return metadata, pitloom_config, config_path

    raise FileNotFoundError(
        f"No pyproject.toml, setup.cfg, or setup.py found in {project_path}"
    )


__all__ = ["read_project"]
