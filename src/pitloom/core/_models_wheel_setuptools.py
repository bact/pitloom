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

import ast
import logging
import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from pitloom.core._models_wheel_types import (
    IncludedFile,
    has_resolvable_pyproject_config,
)

if TYPE_CHECKING:
    from setuptools.command.build_py import build_py as BuildPyCommand
    from setuptools.dist import Distribution

log = logging.getLogger(__name__)

# setup() keyword arguments that decide which files end up in the
# wheel. Static config (pyproject.toml/setup.cfg) can resolve a
# Distribution without ever inspecting setup.py -- but if setup.py
# *also* passes one of these imperatively (a plain literal, a
# find_packages() call, anything), it silently takes precedence in a
# real build. discover() never executes setup.py (see the module
# docstring), so it has no way to know the real value; the best it can
# do is warn that the statically-resolved file list may be incomplete
# or wrong.
_IMPERATIVE_PACKAGING_KWARGS = frozenset(
    {
        "packages",
        "py_modules",
        "package_dir",
        "package_data",
        "include_package_data",
        "exclude_package_data",
        "data_files",
    }
)


@contextmanager
def _chdir(project_dir: Path) -> Iterator[None]:
    """Setuptools' :class:`~setuptools.dist.Distribution`/
    :class:`~setuptools.command.build_py.build_py` resolve paths relative
    to the current working directory, so discovery needs to run from
    *project_dir* for the duration of the call.

    This process-wide ``os.chdir()`` is only safe because
    :mod:`pitloom.core._models_wheel` -- the sole caller of
    :func:`discover` -- runs every call to this function under its
    read/write discovery lock's exclusive write mode, which keeps it
    from overlapping any other backend's discovery call (Hatchling's
    included); this module holds no lock of its own.
    """
    original_cwd = Path.cwd()
    os.chdir(project_dir)
    try:
        yield
    finally:
        os.chdir(original_cwd)


@contextmanager
def _isolated_sys_modules(project_dir: Path) -> Iterator[None]:
    """``[tool.setuptools.dynamic]``/``attr:`` resolution can fall back to
    importing the target project's own module (when static AST-based
    reading of the value fails), caching it in the process-global
    ``sys.modules`` by module name only -- not by file path. Remove any
    module newly imported *from beneath project_dir* during the wrapped
    block once it's done, so a later ``discover()`` call for a
    *different* project with a same-named module doesn't silently reuse
    this project's cached module instead of importing its own. A module
    imported as a side effect from outside *project_dir* (a third-party
    dependency pulled in transitively) is left in place -- evicting it
    has no benefit specific to this project and risks breaking a module
    that isn't safe to import twice in one interpreter (some C
    extensions)."""
    before = set(sys.modules)
    try:
        yield
    finally:
        resolved_project_dir = project_dir.resolve()
        for name in set(sys.modules) - before:
            module = sys.modules.get(name)
            module_file = getattr(module, "__file__", None)
            if module_file is None:
                continue
            try:
                in_project = resolved_project_dir in Path(module_file).resolve().parents
            except (OSError, RuntimeError, ValueError):
                in_project = False
            if in_project:
                del sys.modules[name]


def _load_distribution(
    project_dir: Path, pyproject_data: dict[str, object] | None
) -> Distribution | None:
    """Resolve a setuptools :class:`~setuptools.dist.Distribution` from
    static config only.

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

    *pyproject_data*, when given, is the already-parsed
    ``pyproject.toml`` (see
    :func:`pitloom.extract._setuptools.read_pyproject_toml`) -- pass it
    when the caller already parsed the file, to avoid re-parsing it here.
    """
    # pylint: disable=import-outside-toplevel
    from setuptools.config import pyprojecttoml, setupcfg
    from setuptools.dist import Distribution

    pyproject_path = project_dir / "pyproject.toml"
    setup_cfg_path = project_dir / "setup.cfg"

    if pyproject_data is None and pyproject_path.is_file():
        # pylint: disable-next=import-outside-toplevel
        from pitloom.extract._setuptools import read_pyproject_toml

        pyproject_data = read_pyproject_toml(project_dir)

    has_pyproject = pyproject_data is not None and has_resolvable_pyproject_config(
        pyproject_data, "setuptools"
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

    # apply_configuration() only applies what's explicitly declared --
    # setuptools' zero-config auto-discovery (flat-layout/src-layout
    # package detection for a project with no `packages`/`py_modules`
    # anywhere) is a *separate* mechanism, normally triggered by
    # Distribution.run_command() before running a real command. Since
    # discover() never runs a real command, it must be triggered
    # explicitly here, or a genuine zero-config PEP 621 project (no
    # `[tool.setuptools]` at all) resolves to no packages -- an empty
    # file list, not the "fall back to Hatchling" `None` this module
    # returns for a project with no config at all, so this must run
    # before returning a Distribution as "resolvable".
    # set_defaults is a ConfigDiscovery instance assigned in
    # Distribution.__init__, not a class-level attribute -- types-setuptools
    # doesn't stub it.
    dist.set_defaults()  # type: ignore[attr-defined]
    return dist


def _distribution_path(package: str, filename: str) -> str:
    """Build a wheel-relative, forward-slash-only distribution path for
    *filename* under *package* -- without a leading slash when *package*
    is the top-level (empty) package (e.g. top-level ``py_modules``/
    ``package_data``), and with any backslash normalized regardless of
    source (a malformed ``packages``/``package_dir`` entry, or a
    Windows-style *filename* from setuptools' own file enumeration)."""
    prefix = package.replace(".", "/")
    path = f"{prefix}/{filename}" if prefix else filename
    return path.replace("\\", "/")


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
                distribution_path = _distribution_path(package, filename)
                physical_path = str(Path(src_dir, filename))
                files.append(
                    IncludedFile(
                        path=physical_path, distribution_path=distribution_path
                    )
                )
        return files


def _dedupe_by_distribution_path(
    files: list[IncludedFile], project_dir: Path
) -> list[IncludedFile]:
    """Drop later entries that share a ``distribution_path`` with an
    earlier one -- e.g. a ``package_data`` glob that also matches a
    ``.py`` module already found by :func:`_discover_module_files`.

    Silent when the colliding entries share the same source ``path``
    too (the benign, common case above). Logs a ``WARNING:`` when they
    don't: two *different* source files resolving to the same
    ``distribution_path`` (e.g. overlapping ``package_dir`` entries) is
    a real misconfiguration silently shrinking the wheel's file set --
    only the first one found survives, with no other signal.
    """
    seen: dict[str, IncludedFile] = {}
    for included_file in files:
        existing = seen.get(included_file.distribution_path)
        if existing is None:
            seen[included_file.distribution_path] = included_file
        elif existing.path != included_file.path:
            log.warning(
                "%s: both %s and %s resolve to the same wheel path %s -- "
                "keeping %s, dropping %s",
                project_dir,
                existing.path,
                included_file.path,
                included_file.distribution_path,
                existing.path,
                included_file.path,
            )
    return list(seen.values())


def _setup_py_packaging_kwargs(setup_py_path: Path) -> list[str]:
    """Names of :data:`_IMPERATIVE_PACKAGING_KWARGS` passed to any
    ``setup()``/``setuptools.setup()``-named call found in
    *setup_py_path*, regardless of whether the value itself is a static
    literal -- unlike metadata extraction, this only needs to know a
    packaging-relevant argument was passed at all, not its value. Every
    matching call is inspected, not just the first, so an unrelated
    ``.setup()``-named call earlier in the file (e.g. ``logger.setup()``)
    can't hide the real one. A ``**kwargs`` unpack in a matching call's
    argument list is itself reported (as the literal string
    ``"**kwargs"``) since its contents can't be inspected statically and
    may hide a packaging-relevant argument. An empty list means no
    ``setup.py``, no ``setup()``-named call, or none of these arguments
    (or an unpack) present; never raises (a ``setup.py`` this module
    can't even parse is not this function's problem to report)."""
    # pylint: disable-next=import-outside-toplevel
    from pitloom.extract._setuptools_py import iter_setup_calls

    try:
        tree = ast.parse(
            setup_py_path.read_text(encoding="utf-8"), filename=str(setup_py_path)
        )
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    found: set[str] = set()
    for node in iter_setup_calls(tree):
        for kw in node.keywords:
            if kw.arg is None:
                found.add("**kwargs")
            elif kw.arg in _IMPERATIVE_PACKAGING_KWARGS:
                found.add(kw.arg)
    return sorted(found)


def _warn_if_setup_py_overrides_packaging(project_dir: Path) -> None:
    """Log a warning when *project_dir*'s ``setup.py`` passes any
    file-selection argument imperatively. Static config can still
    resolve *a* file list in this case (so :func:`discover` returns it,
    not ``None``) -- but since ``setup.py`` is never executed, that list
    may be silently incomplete or wrong relative to what a real build
    would produce, and there is no way to tell without running it."""
    setup_py_path = project_dir / "setup.py"
    if not setup_py_path.is_file():
        return
    imperative_kwargs = _setup_py_packaging_kwargs(setup_py_path)
    if imperative_kwargs:
        log.warning(
            "%s's setup.py passes %s imperatively -- the file list "
            "resolved statically from pyproject.toml/setup.cfg alone "
            "may be incomplete or inaccurate for this project",
            project_dir,
            ", ".join(imperative_kwargs),
        )


def discover(
    project_dir: Path, *, pyproject_data: dict[str, object] | None = None
) -> list[IncludedFile] | None:
    """Discover a setuptools wheel's file set from static config only.

    Returns ``None`` when there's no static ``pyproject.toml``/
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

    # pylint: disable-next=import-outside-toplevel
    from setuptools.errors import PackageDiscoveryError

    try:
        with _chdir(project_dir):
            with _isolated_sys_modules(project_dir):
                dist = _load_distribution(project_dir, pyproject_data)
            if dist is None:
                return None

            build_py_cmd = build_py(dist)
            build_py_cmd.finalize_options()
            files = _dedupe_by_distribution_path(
                _discover_module_files(build_py_cmd)
                + _discover_data_files(build_py_cmd),
                project_dir,
            )
            _warn_if_setup_py_overrides_packaging(project_dir)
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
    except PackageDiscoveryError as exc:
        log.warning(
            "%s: setuptools could not auto-discover packages unambiguously "
            "(%s) -- specify `packages`/`py_modules` explicitly in "
            "pyproject.toml or setup.cfg; falling back to Hatchling-based "
            "heuristic",
            project_dir,
            exc,
        )
        return None
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        log.warning("Setuptools file discovery failed for %s: %s", project_dir, exc)
        return None
