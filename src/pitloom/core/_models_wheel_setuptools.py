# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Setuptools-backed wheel file discovery, from static config only.

Resolves ``packages``/``packages.find``/``package_dir``/``package_data``/
``include_package_data`` via setuptools' own config-resolution API
(``setuptools.config.pyprojecttoml``/``setupcfg``), applying both
``setup.cfg`` and ``pyproject.toml`` when present (not mutually
exclusive) the same way a real setuptools build would -- without
executing ``setup.py``. A project with neither file (packages only
resolvable by running an imperative ``setup.py``) is out of scope,
matching :mod:`pitloom.extract._setuptools`'s existing
static-analysis-only boundary; see
``working-docs/implementation/sbom-lifecycle-stages.md`` for the full
rationale.

See also: :mod:`pitloom.core._models_wheel` (dispatch facade),
:mod:`pitloom.core._models_wheel_types`.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from pitloom.core._models_wheel_types import IncludedFile

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

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


def _has_resolvable_pyproject_config(pyproject_path: Path) -> bool:
    """Whether *pyproject_path* declares enough for setuptools to
    resolve packages from: a PEP 621 ``[project]`` table (setuptools'
    own zero-config auto-discovery applies here even without an
    explicit ``[tool.setuptools]`` table) or an explicit
    ``[tool.setuptools]`` table. A ``pyproject.toml`` with only
    ``[build-system]`` (e.g. packages declared imperatively in
    ``setup.py`` instead) declares neither."""
    try:
        with pyproject_path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    tool = data.get("tool", {})
    return "project" in data or (
        "setuptools" in tool if isinstance(tool, dict) else False
    )


def _load_distribution(project_dir: Path) -> Distribution | None:
    """Resolve a setuptools ``Distribution`` from static config only.

    Must run with the process cwd already set to *project_dir* (see the
    ``_chdir`` caller in :func:`discover`): ``apply_configuration()`` is
    what performs ``[tool.setuptools.dynamic]``/``attr:`` resolution,
    which can import the target project's own modules -- running it
    with the wrong cwd risks resolving that import against an unrelated
    module reachable from Pitloom's own cwd/``sys.path`` instead of the
    intended one, silently reading the wrong package's data.

    ``setup.cfg`` is applied first (legacy config as a base), then
    ``pyproject.toml`` on top -- matching how a real setuptools build
    consults both rather than treating them as mutually exclusive.
    """
    # pylint: disable=import-outside-toplevel
    from setuptools.config import pyprojecttoml, setupcfg
    from setuptools.dist import Distribution

    pyproject_path = project_dir / "pyproject.toml"
    setup_cfg_path = project_dir / "setup.cfg"
    has_pyproject = pyproject_path.is_file() and _has_resolvable_pyproject_config(
        pyproject_path
    )
    has_setup_cfg = setup_cfg_path.is_file()
    if not has_pyproject and not has_setup_cfg:
        return None

    dist = Distribution()
    dist.script_name = "setup.py"

    if has_setup_cfg:
        setupcfg.apply_configuration(dist, str(setup_cfg_path))
    if has_pyproject:
        pyprojecttoml.apply_configuration(dist, str(pyproject_path))
    return dist


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


def discover(project_dir: Path) -> list[IncludedFile] | None:
    """Discover a setuptools wheel's file set from static config only.

    Returns ``None`` when there's no static ``pyproject.toml``/
    ``setup.cfg`` config to resolve from, or on any setuptools
    introspection failure -- both signal "fall back", not "found zero
    files".
    """
    # pylint: disable=import-outside-toplevel
    from setuptools.command.build_py import build_py

    try:
        with _DISCOVERY_LOCK, _chdir(project_dir):
            dist = _load_distribution(project_dir)
            if dist is None:
                return None

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
