# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python project metadata from setup.cfg and setup.py.

Supports setuptools-based projects that declare metadata in ``setup.cfg``
(configparser format) or ``setup.py`` (AST-parsed).  When both files exist,
``setup.cfg`` values take precedence, following setuptools conventions.

.. rubric:: Conflict resolution

When multiple sources are present, fields are merged with this priority order
(highest to lowest):

1. ``pyproject.toml [project]`` -- handled upstream by
   :func:`~pitloom.extract._pyproject.read_pyproject`; merged via
   :func:`~pitloom.core.project.merge_project_metadata` by the assembler.
2. ``setup.cfg [metadata]`` / ``[options]``
3. ``setup.py`` ``setup()`` keyword arguments (AST-extracted literals only)

For each field the highest-priority non-empty value wins; provenance is
recorded per field so consumers can audit the source.

.. rubric:: Limitations (static analysis)

- Dynamic values in ``setup.py`` (variables, function calls, conditional
  expressions) are **not resolvable** -- they are silently skipped.
- ``version = attr: package.__version__`` in ``setup.cfg`` uses best-effort
  file scanning via AST parsing of the referenced module file.
- Build-time metadata obtained via PEP 517
  ``prepare_metadata_for_build_wheel`` may differ from statically extracted
  values.  PEP 517 integration is planned as a future enhancement.

See Also:
    https://setuptools.pypa.io/en/latest/userguide/declarative_config.html
    https://peps.python.org/pep-0517/
    :mod:`pitloom.extract._setuptools_cfg` (setup.cfg parsing)
    :mod:`pitloom.extract._setuptools_py` (setup.py AST parsing)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from pitloom.core.config import PitloomConfig
from pitloom.core.project import ProjectMetadata, merge_project_metadata
from pitloom.extract._license import (
    detect_license_for_project,
    resolve_license_concluded,
)
from pitloom.extract._setuptools_cfg import (
    _DIRECTIVE_RE,
    _NoProjectNameError,
    _read_pitloom_config_from_cfg,
    _resolve_cfg_version,
    _section_dict,
    read_setup_cfg,
)
from pitloom.extract._setuptools_py import (
    _ast_literal,
    _extract_setup_kwargs,
    read_setup_py,
)

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

log = logging.getLogger(__name__)

__all__ = [
    "_DIRECTIVE_RE",
    "_NoProjectNameError",
    "_ast_literal",
    "_extract_setup_kwargs",
    "_read_pitloom_config_from_cfg",
    "_resolve_cfg_version",
    "_section_dict",
    "detect_build_backend",
    "read_setup_cfg",
    "read_setup_py",
    "read_setuptools",
]


def detect_build_backend(project_dir: Path) -> str | None:
    """Detect the build backend declared in ``pyproject.toml``.

    Reads the ``[build-system] build-backend`` field and returns a
    lower-case identifier.  Falls back to ``"setuptools"`` when no
    ``pyproject.toml`` is present but ``setup.cfg`` or ``setup.py`` exists.
    """
    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        if (project_dir / "setup.cfg").exists() or (project_dir / "setup.py").exists():
            return "setuptools"
        return None

    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        build_backend: str = data.get("build-system", {}).get("build-backend", "")
        for backend in ("setuptools", "hatchling", "flit", "poetry", "pdm"):
            if backend in build_backend:
                return backend
        if build_backend:
            return build_backend.split(".")[0].lower()
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        log.debug("Failed to detect build backend from %s: %s", pyproject_path, exc)
    return None


def read_setuptools(project_dir: Path) -> tuple[ProjectMetadata, PitloomConfig]:
    """Read project metadata from ``setup.cfg`` and/or ``setup.py``.

    Merges metadata from both files with ``setup.cfg`` taking precedence
    over ``setup.py``, following modern setuptools conventions.
    """
    setup_cfg = project_dir / "setup.cfg"
    setup_py = project_dir / "setup.py"

    cfg_metadata: ProjectMetadata | None = None
    cfg_config: PitloomConfig = PitloomConfig()
    py_metadata: ProjectMetadata | None = None

    if setup_cfg.exists():
        try:
            cfg_metadata, cfg_config = read_setup_cfg(project_dir)
        except (FileNotFoundError, _NoProjectNameError):
            pass

    if setup_py.exists():
        try:
            py_metadata, _ = read_setup_py(project_dir)
        except (FileNotFoundError, ValueError):
            pass

    if cfg_metadata is None and py_metadata is None:
        raise FileNotFoundError(
            f"No usable project metadata found in {project_dir}. "
            "Expected setup.cfg [metadata] name or setup.py setup(name=...)."
        )

    if cfg_metadata is not None and py_metadata is not None:
        metadata = merge_project_metadata(cfg_metadata, py_metadata)
    elif cfg_metadata is not None:
        metadata = cfg_metadata
    else:
        if py_metadata is None:
            raise RuntimeError("unreachable: py_metadata must be set here")
        metadata = py_metadata
        cfg_config = PitloomConfig()

    metadata = _resolve_setuptools_license(metadata, project_dir)
    return metadata, cfg_config


def _resolve_setuptools_license(
    metadata: ProjectMetadata, project_dir: Path
) -> ProjectMetadata:
    """Apply license resolution to merged setup.cfg/setup.py result."""
    if metadata.license_name:
        concluded, concluded_prov = resolve_license_concluded(True, project_dir)
        if concluded and concluded_prov:
            metadata.license_concluded = concluded
            metadata.provenance["license_concluded"] = concluded_prov
        return metadata

    detected, detected_prov = detect_license_for_project(project_dir)
    if detected:
        metadata.license_name = detected
        if detected_prov:
            metadata.provenance["license"] = detected_prov
    return metadata
