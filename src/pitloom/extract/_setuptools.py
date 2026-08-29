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
    "read_pyproject_toml",
    "read_setup_cfg",
    "read_setup_py",
    "read_setuptools",
]


# Top-level module name (the part before the first "." or ":" in
# `build-backend`) -> canonical short identifier, for the handful of
# well-known backends whose top-level module doesn't already match the
# identifier pitloom uses for them elsewhere (e.g. "flit_core" for flit).
_KNOWN_BACKEND_ALIASES = {
    "setuptools": "setuptools",
    "hatchling": "hatchling",
    "flit_core": "flit",
    "poetry": "poetry",
    "pdm": "pdm",
}


def read_pyproject_toml(project_dir: Path) -> dict[str, object] | None:
    """Parse *project_dir*'s ``pyproject.toml``, or ``None`` if missing/invalid.

    Callers that need more than one fact out of ``pyproject.toml`` (e.g.
    both the declared build backend and setuptools' own static-config
    resolvability) should call this once and pass the result to
    :func:`detect_build_backend` rather than each re-parsing the file.
    """
    pyproject_path = project_dir / "pyproject.toml"
    try:
        with open(pyproject_path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        log.debug("Failed to parse %s: %s", pyproject_path, exc)
        return None


def _detect_setuptools_from_legacy_files(project_dir: Path) -> str | None:
    """``"setuptools"`` when *project_dir* has a ``setup.cfg``/``setup.py``
    to back it up, else ``None`` -- the shared fallback for every case
    where no ``build-backend`` value is resolvable from ``pyproject.toml``
    (absent, unparseable, or present but without a ``build-backend``
    key)."""
    if (project_dir / "setup.cfg").exists() or (project_dir / "setup.py").exists():
        return "setuptools"
    return None


# pylint: disable-next=too-few-public-methods
class _NotGiven:
    """Sentinel distinguishing "caller passed no ``pyproject_data`` at all,
    please read the file yourself" from an explicit ``pyproject_data=None``
    ("I already tried reading it and got nothing -- don't retry")."""

    __slots__ = ()


_NOT_GIVEN = _NotGiven()


def detect_build_backend(
    project_dir: Path,
    *,
    pyproject_data: dict[str, object] | None | _NotGiven = _NOT_GIVEN,
) -> str | None:
    """Detect the build backend declared in ``pyproject.toml``.

    Reads the ``[build-system] build-backend`` field and returns a
    lower-case identifier, matched on its top-level module name (the
    part before the first ``.``/``:``) -- not a substring match, so a
    backend like ``"my_setuptools_shim.api"`` is never misdetected as
    ``"setuptools"``. Falls back to ``"setuptools"`` when ``setup.cfg``
    or ``setup.py`` exists and no ``build-backend`` value is resolvable
    -- because ``pyproject.toml`` is entirely absent, because it exists
    but is unparseable, or because it exists but has no
    ``build-backend`` key (a legacy PEP 518-only ``[build-system]``
    declaration, which is still a real setuptools project).

    *pyproject_data*, when omitted, is read and parsed here. Pass the
    result of a prior :func:`read_pyproject_toml` call instead when the
    caller already has one -- including an explicit ``None`` when that
    prior call already failed (missing/unparseable file); passing the
    already-``None`` result back avoids re-reading and re-parsing the
    same broken file a second time for the same answer.
    """
    pyproject_path = project_dir / "pyproject.toml"
    data: dict[str, object] | None
    if isinstance(pyproject_data, _NotGiven):
        if not pyproject_path.exists():
            return _detect_setuptools_from_legacy_files(project_dir)
        data = read_pyproject_toml(project_dir)
        if data is None:
            return _detect_setuptools_from_legacy_files(project_dir)
    else:
        data = pyproject_data
        if data is None:
            return _detect_setuptools_from_legacy_files(project_dir)

    build_system = data.get("build-system", {})
    build_backend = ""
    if isinstance(build_system, dict):
        raw_backend = build_system.get("build-backend", "")
        if isinstance(raw_backend, str):
            build_backend = raw_backend
    if not build_backend:
        # PEP 518-only pyproject.toml (no build-backend key) -- still a
        # real setuptools project if setup.cfg/setup.py back it up, same
        # fallback as when pyproject.toml is absent entirely.
        return _detect_setuptools_from_legacy_files(project_dir)
    top_level = build_backend.split(":")[0].split(".")[0].lower()
    return _KNOWN_BACKEND_ALIASES.get(top_level, top_level)


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
        if py_metadata is None:  # pragma: no cover
            # Type-narrowing only: the guard above already proved that
            # when cfg_metadata is None, py_metadata cannot also be None.
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
