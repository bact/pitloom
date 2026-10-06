# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python project metadata from setup.cfg and setup.py.

Supports setuptools-based projects that declare metadata in ``setup.cfg``
(configparser format) or ``setup.py`` (AST-parsed). When both files exist,
a non-empty ``setup()`` keyword overrides the same ``setup.cfg`` option, as
setuptools does; :mod:`pitloom.extract.project._setuptools_options` has the
rule and its one difference (a placeholder licence gives way). A
``pyproject.toml [project]`` table is read before both, upstream
(:func:`~pitloom.extract.project.read_project`). Provenance is recorded per
field.

.. rubric:: Limitations (static analysis)

- Dynamic values in ``setup.py`` (variables, function calls, conditional
  expressions) are **not resolvable** -- each is skipped with a
  ``WARNING:`` and ``setup.cfg``'s value is used.
- ``version = attr: package.__version__`` in ``setup.cfg`` uses best-effort
  file scanning via AST parsing of the referenced module file.
- Build-time metadata obtained via PEP 517
  ``prepare_metadata_for_build_wheel`` may differ from statically extracted
  values.  PEP 517 integration is planned as a future enhancement.

See Also:
    https://setuptools.pypa.io/en/latest/userguide/declarative_config.html
    https://peps.python.org/pep-0517/
    :mod:`pitloom.extract.project.setuptools_cfg` (setup.cfg parsing)
    :mod:`pitloom.extract.project.setuptools_py` (setup.py AST parsing)
"""

from __future__ import annotations

import logging
from pathlib import Path

from pitloom._toml_io import TOMLDecodeError, load_toml_file
from pitloom.core.config import PitloomConfig
from pitloom.core.project import ProjectMetadata
from pitloom.extract._license import (
    apply_in_package_license,
    collect_license_candidates,
)
from pitloom.extract.project._setup_cfg_directives import (
    _DIRECTIVE_RE,
    _resolve_cfg_version,
)
from pitloom.extract.project._setuptools_options import (
    ConflictReport,
    SetupOptions,
    build_setuptools_metadata,
    record_setuptools_conflicts,
)
from pitloom.extract.project.setuptools_cfg import (
    _NoProjectNameError,
    _read_pitloom_config_from_cfg,
    _section_dict,
    read_setup_cfg,
    read_setup_cfg_options,
)
from pitloom.extract.project.setuptools_py import (
    _ast_literal,
    _extract_setup_kwargs,
    read_setup_py,
    read_setup_py_options,
)

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
        return load_toml_file(pyproject_path)
    except (OSError, TOMLDecodeError) as exc:
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


def _read_cfg_options(
    project_dir: Path, read_config: bool
) -> tuple[SetupOptions, PitloomConfig]:
    try:
        return read_setup_cfg_options(project_dir, read_config=read_config)
    except FileNotFoundError:
        return {}, PitloomConfig()


def _read_py_options(
    project_dir: Path, cfg: SetupOptions, *, quiet: bool
) -> SetupOptions:
    """``setup.py``'s options; none, with a ``WARNING:`` when *cfg* names
    the project, when it cannot be parsed."""
    try:
        return read_setup_py_options(project_dir, quiet=quiet)
    except FileNotFoundError:
        return {}
    except ValueError as exc:
        name = cfg.get("name")
        if name is not None and name.value and not quiet:
            log.warning("%s: %s -- reading setup.cfg alone", project_dir, exc)
        return {}


def read_setuptools(
    project_dir: Path, *, quiet: bool = False, read_config: bool = True
) -> tuple[ProjectMetadata, PitloomConfig]:
    """Read project metadata from ``setup.cfg`` and/or ``setup.py``, a
    ``setup()`` keyword overriding the ``setup.cfg`` option as setuptools
    does (:mod:`pitloom.extract.project._setuptools_options`); a real value
    overridden is recorded as a conflict.

    ``quiet`` suppresses this read's own ``WARNING:`` lines (default
    ``False``) -- for a caller re-reading the same project a second time;
    see :func:`pitloom.extract.project.read_project`'s own ``quiet``.
    Without *read_config*, ``[tool:pitloom]`` is not parsed (see
    :func:`read_setup_cfg`); it is parsed only when ``setup.cfg`` names the
    project.

    Raises:
        FileNotFoundError: neither file names the project.
    """
    cfg_options, config = _read_cfg_options(project_dir, read_config)
    py_options = _read_py_options(project_dir, cfg_options, quiet=quiet)
    metadata = build_setuptools_metadata(cfg_options, py_options)
    if not metadata.name:
        raise FileNotFoundError(
            f"No usable project metadata found in {project_dir}. "
            "Expected setup.cfg [metadata] name or a literal setup.py "
            "setup(name=...)."
        )
    record_setuptools_conflicts(
        metadata, cfg_options, py_options, ConflictReport(str(project_dir), quiet)
    )
    apply_in_package_license(metadata, collect_license_candidates(project_dir))
    return metadata, config
