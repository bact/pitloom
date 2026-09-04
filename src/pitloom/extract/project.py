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
from pitloom.extract._locked_dependencies import apply_locked_dependencies
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
    *,
    include_locked_dependencies: bool = True,
) -> tuple[ProjectMetadata, PitloomConfig, Path | None]:
    """Resolve project metadata and Pitloom config from *project_path*.

    If *project_path* is a source distribution archive (.tar.gz, .zip),
    extracts metadata from its internal PKG-INFO or pyproject.toml.
    Otherwise, treats *project_path* as a directory and tries
    ``pyproject.toml`` first, then ``setup.cfg``/``setup.py``.

    For every directory-based resolution (not the sdist-archive case),
    also overlays a sibling lock/pin file's resolved dependencies onto
    the result via a single, shared call to
    :func:`pitloom.extract._locked_dependencies.apply_locked_dependencies`
    -- applied uniformly regardless of which metadata source won, since
    some lock formats (``Pipfile.lock``, pinned ``requirements.txt``)
    pair with a bare ``setup.py`` in real projects, never ``pyproject.toml``.

    ``include_locked_dependencies`` lets a build-stage or config-only
    caller (e.g. ``embed-wheel``, or a shared CLI helper that only wants
    ``[tool.pitloom]`` settings and discards the metadata) explicitly opt
    out of *every* lock/pin source -- source-stage lock/pin data must
    never leak into a build-stage SBOM, and skipping this also skips its
    file I/O for a caller that would discard the result anyway. It's
    forwarded to :func:`pitloom.extract._pyproject.read_pyproject` (which
    forwards it again to
    :func:`pitloom.extract._pyproject._try_read_poetry` for
    ``poetry.lock``, gated by that function's own identically-named
    parameter) *and* used directly here to gate
    :func:`pitloom.extract._locked_dependencies.apply_locked_dependencies`
    for every other format -- one flag controls both, not two
    independently-set ones that happen to share a name.

    Args:
        project_path: Project root directory or sdist archive path.
        include_locked_dependencies: Whether to read any lock/pin file's
            resolved dependencies at all -- ``poetry.lock`` included
            (default ``True``). Pass ``False`` from any build-stage or
            metadata-discarding caller.

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

    config_path: Path | None
    pyproject_path = project_path / "pyproject.toml"
    if pyproject_path.exists():
        metadata, pitloom_config = read_pyproject(
            pyproject_path, include_locked_dependencies=include_locked_dependencies
        )
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
        else:
            config_path = pyproject_path
    elif setup_cfg.exists() or setup_py.exists():
        metadata, pitloom_config = read_setuptools(project_path)
        config_path = setup_cfg if setup_cfg.exists() else setup_py
    else:
        raise FileNotFoundError(
            f"No pyproject.toml, setup.cfg, or setup.py found in {project_path}"
        )

    if include_locked_dependencies:
        apply_locked_dependencies(metadata, project_path)
    return metadata, pitloom_config, config_path


__all__ = ["read_project"]
