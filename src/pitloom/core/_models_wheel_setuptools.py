# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Setuptools-backed wheel file discovery, from static config only.

Resolves ``packages``/``packages.find``/``package_dir``/``package_data``/
``include_package_data`` via setuptools' own config-resolution API
(``setuptools.config.pyprojecttoml``/``setupcfg``), the same way a real
setuptools build would -- without executing ``setup.py``. A project
with no static config (packages only resolvable by running an
imperative ``setup.py``) is out of scope, matching
:mod:`pitloom.extract._setuptools`'s existing static-analysis-only
boundary; see ``working-docs/implementation/sbom-lifecycle-stages.md``
for the full rationale.

See also: :mod:`pitloom.core._models_wheel` (dispatch facade),
:mod:`pitloom.core._models_wheel_types`.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from pitloom.core._models_wheel_types import IncludedFile

if TYPE_CHECKING:
    from setuptools.command.build_py import build_py as BuildPyCommand
    from setuptools.dist import Distribution

log = logging.getLogger(__name__)

# Serializes discovery calls that rely on the process-wide cwd (see
# `_chdir`) -- concurrent `discover()` calls would otherwise race on
# `os.chdir()`.
_DISCOVERY_LOCK = threading.Lock()


@contextmanager
def _chdir(project_dir: Path) -> Iterator[None]:
    """Setuptools' ``Distribution``/``build_py`` resolve paths relative to
    the current working directory, so discovery needs to run from
    *project_dir* for the duration of the call."""
    original_cwd = Path.cwd()
    os.chdir(project_dir)
    try:
        yield
    finally:
        os.chdir(original_cwd)


def _has_setuptools_pyproject_config(pyproject_data: dict[str, object]) -> bool:
    """Whether the parsed ``pyproject.toml`` declares static
    ``[tool.setuptools]`` config, as opposed to only ``[build-system]``."""
    tool = pyproject_data.get("tool", {})
    return isinstance(tool, dict) and "setuptools" in tool


def _load_distribution(
    project_dir: Path, pyproject_data: dict[str, object] | None
) -> Distribution | None:
    # pylint: disable=import-outside-toplevel
    from setuptools.config import pyprojecttoml, setupcfg
    from setuptools.dist import Distribution

    dist = Distribution()
    dist.script_name = "setup.py"

    pyproject_path = project_dir / "pyproject.toml"
    setup_cfg_path = project_dir / "setup.cfg"

    if pyproject_data is None and pyproject_path.is_file():
        # pylint: disable-next=import-outside-toplevel
        from pitloom.extract._setuptools import read_pyproject_toml

        pyproject_data = read_pyproject_toml(project_dir)

    if pyproject_data is not None and _has_setuptools_pyproject_config(pyproject_data):
        pyprojecttoml.apply_configuration(dist, str(pyproject_path))
        return dist
    if setup_cfg_path.is_file():
        setupcfg.apply_configuration(dist, str(setup_cfg_path))
        return dist
    return None


def _distribution_path(package: str, filename: str) -> str:
    """Build a wheel-relative distribution path for *filename* under
    *package*, without a leading slash when *package* is the top-level
    (empty) package -- e.g. top-level ``py_modules``/``package_data``."""
    prefix = package.replace(".", "/")
    return f"{prefix}/{filename}" if prefix else filename


def _discover_module_files(build_py_cmd: BuildPyCommand) -> list[IncludedFile]:
    files: list[IncludedFile] = []
    # find_all_modules is inherited from distutils' build_py, which
    # types-setuptools doesn't stub.
    modules = build_py_cmd.find_all_modules()  # type: ignore[no-untyped-call]
    for package, _module, module_file in modules:
        distribution_path = _distribution_path(package, Path(module_file).name)
        files.append(
            IncludedFile(path=module_file, distribution_path=distribution_path)
        )
    return files


def _discover_data_files(build_py_cmd: BuildPyCommand) -> list[IncludedFile]:
    """Resolve ``package_data``/``include_package_data`` (MANIFEST.in-driven)
    files. ``include_package_data`` requires setuptools' own manifest
    analysis, which invokes the real ``egg_info`` command -- redirected
    to a temp directory via ``egg_base`` so *project_dir* is never
    mutated by this read-only discovery pass."""
    with tempfile.TemporaryDirectory() as egg_base:
        egg_info_cmd = build_py_cmd.distribution.get_command_obj("egg_info")
        egg_info_cmd.egg_base = egg_base

        files: list[IncludedFile] = []
        # pylint: disable-next=protected-access
        for package, src_dir, _build_dir, filenames in build_py_cmd._get_data_files():
            for filename in filenames:
                distribution_path = _distribution_path(package, filename).replace(
                    "\\", "/"
                )
                physical_path = str(Path(src_dir, filename))
                files.append(
                    IncludedFile(
                        path=physical_path, distribution_path=distribution_path
                    )
                )
        return files


def _dedupe_by_distribution_path(files: list[IncludedFile]) -> list[IncludedFile]:
    """Drop later entries that share a ``distribution_path`` with an
    earlier one -- e.g. a ``package_data`` glob that also matches a
    ``.py`` module already found by :func:`_discover_module_files`."""
    seen: dict[str, IncludedFile] = {}
    for included_file in files:
        seen.setdefault(included_file.distribution_path, included_file)
    return list(seen.values())


def discover(
    project_dir: Path, *, pyproject_data: dict[str, object] | None = None
) -> list[IncludedFile] | None:
    """Discover a setuptools wheel's file set from static config only.

    Returns ``None`` when there's no static ``[tool.setuptools]``/
    ``setup.cfg`` config to resolve from, or on any setuptools
    introspection failure -- both signal "fall back", not "found zero
    files".

    *pyproject_data*, when given, is the already-parsed
    ``pyproject.toml`` (see
    :func:`pitloom.extract._setuptools.read_pyproject_toml`) -- pass it
    when the caller already parsed the file, to avoid re-parsing it here.
    """
    # pylint: disable=import-outside-toplevel
    from setuptools.command.build_py import build_py

    try:
        dist = _load_distribution(project_dir, pyproject_data)
        if dist is None:
            return None

        with _DISCOVERY_LOCK, _chdir(project_dir):
            build_py_cmd = build_py(dist)
            build_py_cmd.finalize_options()
            files = _dedupe_by_distribution_path(
                _discover_module_files(build_py_cmd)
                + _discover_data_files(build_py_cmd)
            )
            # Resolve to absolute paths while still inside project_dir --
            # matches Hatchling's IncludedFile.path contract ("the
            # absolute path"), since the caller reads these after this
            # context manager has already restored the original cwd.
            return [
                IncludedFile(
                    path=str(Path(f.path).resolve()),
                    distribution_path=f.distribution_path,
                )
                for f in files
            ]
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        log.warning("Setuptools file discovery failed for %s: %s", project_dir, exc)
        return None
