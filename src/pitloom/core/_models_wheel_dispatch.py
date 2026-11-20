# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Backend dispatch for wheel file discovery.

Resolves *which* discovery path a project's build backend should use --
a registered backend's own static module, the generic
:mod:`pitloom.core._models_wheel_build_and_read` mechanism (gated behind
``--allow-build``), or the Hatchling-based heuristic fallback -- and
returns the resolved files. Split out of :mod:`pitloom.core._models_wheel`
once that file crossed the ~400-500 line soft limit; the shared per-file
hashing/extraction loop stays there, this module owns only the dispatch
decision.

See also: :mod:`pitloom.core._models_wheel`'s ``get_wheel_files()``, the
sole caller of :func:`_discover_included_files` below.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Final, NamedTuple

from pitloom.core import _models_wheel_hatchling
from pitloom.core._models_wheel_lock import _DISCOVERY_LOCK
from pitloom.core._models_wheel_types import (
    BackendDiscoverer,
    BuildSettings,
    IncludedFile,
    has_resolvable_pyproject_config,
    has_uv_build_backend_overrides,
    take_discovery_failure,
)
from pitloom.messages import BUILD_FRAME, emit
from pitloom.messages.build import BUILD_CODE_UNSAFE, unsafe_line
from pitloom.messages.file_discovery import (
    BUILD_FAILED_LINE,
    BUILD_FAILED_NO_PROJECT_LINE,
    FAILED_HEURISTIC_LINE,
    FAILED_NO_PROJECT_LINE,
    INTROSPECTION_LINE,
    NO_STATIC_HEURISTIC_LINE,
    NO_STATIC_LINE,
    NOT_AWARE_LINE,
    NOT_AWARE_NO_PROJECT_LINE,
    UV_OVERRIDES_LINE,
    warn_discovery,
)

log = logging.getLogger(__name__)


#: The display name of each registered backend's discoverer, by backend key.
_DISCOVERER_NAMES: Final = {
    "setuptools": "Setuptools",
    "poetry": "Poetry",
    "flit": "Flit",
    "pdm": "PDM",
}


class _RegisteredBackend(NamedTuple):
    """One entry in the registered-backend dispatch table.

    ``needs_write_lock`` is a required field, not a separately-maintained
    allowlist elsewhere in this module (the shape this replaced --
    ``_WRITER_BACKENDS``, a standalone ``frozenset`` linked to each
    backend module only by a docstring comment) -- registering a new
    backend here forces the write-lock decision to be made at the same
    call site, instead of leaving it to default silently to "reader" if
    a second, distant data structure is forgotten."""

    discoverer: BackendDiscoverer
    needs_write_lock: bool


def _has_project_table(pyproject_data: dict[str, object] | None) -> bool:
    """Whether *pyproject_data* declares a ``[project]`` table.

    :func:`_skip_hatchling_fallback` and :func:`_discover_with_no_static_module`
    both use it to decide whether Hatchling's ``WheelBuilder``, which requires
    a ``[project]`` table, is worth attempting.
    """
    return pyproject_data is not None and "project" in pyproject_data


def _skip_hatchling_fallback(
    backend: str,
    pyproject_data: dict[str, object] | None,
    project_dir: Path,
    *,
    failed: bool = False,
) -> bool:
    """Log the right ``WARNING:`` for a backend discoverer giving up
    (returning ``None``), and report whether the doomed Hatchling
    fallback attempt should be skipped entirely (``True``) or still
    tried (``False``).

    Hatchling's ``WheelBuilder`` requires a ``pyproject.toml``
    ``[project]`` table -- with none present at all, it is guaranteed to
    also fail, so the confusing "Hatchling"-branded error for a project
    that has nothing to do with Hatchling isn't worth it. Distinguishing
    *why* the backend's own discoverer already gave up -- a
    ``[tool.<backend>]`` table present (approximate but the best
    available signal -- every currently-registered backend names its
    config table after itself) means static config existed but
    introspection itself failed, not that nothing was declared at all --
    only changes the warning's wording, not this return value. With *failed*
    (the discoverer already logged ``file discovery failed``) the wording
    does not claim the config is absent.
    """
    name = _DISCOVERER_NAMES[backend]
    if _has_project_table(pyproject_data):
        if failed:
            warn_discovery(log, FAILED_HEURISTIC_LINE, dir=project_dir)
        else:
            warn_discovery(
                log, NO_STATIC_HEURISTIC_LINE, dir=project_dir, discoverer=name
            )
        return False

    if pyproject_data is not None and has_resolvable_pyproject_config(
        pyproject_data, backend
    ):
        warn_discovery(log, INTROSPECTION_LINE, dir=project_dir, discoverer=name)
    elif failed:
        warn_discovery(log, FAILED_NO_PROJECT_LINE, dir=project_dir)
    else:
        warn_discovery(log, NO_STATIC_LINE, dir=project_dir, discoverer=name)
    return True


def _uv_overrides_unseen(
    backend: str, pyproject_data: dict[str, object] | None, *, allow_build: bool
) -> bool:
    """Whether the "not backend-aware" fallback ``WARNING:`` below is
    followed by the ``uv_build`` hint -- true only for the one known,
    confirmed divergence risk (see
    :func:`~pitloom.core._models_wheel_types.has_uv_build_backend_overrides`'s
    docstring), never a general "you might want --allow-build" nudge.

    Suppressed when *allow_build* is already ``True``: this call site is
    only reached after build-and-read was already tried and failed (see
    :func:`_discover_with_no_static_module`), so suggesting the user pass
    a flag they already passed -- and that just failed -- would be
    self-contradictory, not a genuine hint.
    """
    return (
        not allow_build
        and backend == "uv_build"
        and pyproject_data is not None
        and has_uv_build_backend_overrides(pyproject_data)
    )


def _noop_cleanup() -> None:
    """Cleanup for every discovery path that never allocates a temp
    directory -- i.e. every path except a successful build-and-read."""


def _try_build_and_read(
    backend: str,
    project_dir: Path,
    *,
    build: BuildSettings,
    static_failed: bool,
) -> tuple[list[IncludedFile], Callable[[], None]] | None:
    """Shared entry point for both ``--allow-build`` call sites in
    :func:`_discover_included_files`: logs the one security-relevant
    ``WARNING:`` (``build-code-unsafe``; its line says whether the
    backend's own discoverer failed, *static_failed*, or it has none, and
    whether the build is isolated), then delegates to the
    generic, backend-agnostic
    :func:`~pitloom.core._models_wheel_build_and_read.build_and_read_wheel`.

    Never invoked unless *build* is not ``None`` at the caller (i.e.
    ``--allow-build`` was given) -- enforced by the caller, not here, so
    this function takes a required
    :class:`~pitloom.core._models_wheel_types.BuildSettings` instead of
    an optional one to accidentally forget to check.
    """
    # pylint: disable-next=import-outside-toplevel
    from pitloom.core._models_wheel_build_and_read import build_and_read_wheel

    emit(
        log,
        BUILD_CODE_UNSAFE,
        logging.WARNING,
        line=unsafe_line(static_failed=static_failed, isolated=build.isolated),
        frame=BUILD_FRAME,
        dir=project_dir,
        backend=backend,
        seconds=build.timeout,
    )
    return build_and_read_wheel(
        project_dir, isolated=build.isolated, timeout=build.timeout
    )


def _discover_with_no_static_module(
    backend: str,
    project_dir: Path,
    pyproject_data: dict[str, object] | None,
    *,
    build: BuildSettings | None,
) -> tuple[list[IncludedFile], Callable[[], None]] | None:
    """No static module for this backend at all: ``uv_build``, an
    unrecognised backend, or a Track B backend (maturin, scikit-build-core,
    meson-python). With *build* given (``--allow-build``) the generic
    build-and-read mechanism handles any of them.

    Returns a result to return immediately, or ``None`` to fall through
    to the Hatchling heuristic (the "not backend-aware" ``WARNING:`` is
    logged here either way before falling through)."""
    if build is not None:
        build_result = _try_build_and_read(
            backend,
            project_dir,
            build=build,
            static_failed=False,
        )
        if build_result is not None:
            return build_result
        # _try_build_and_read/build_and_read_wheel() already logged its
        # own specific failure WARNING:; fall through to the generic
        # "not backend-aware" warning.
    has_project = _has_project_table(pyproject_data)
    if build is None:
        line = NOT_AWARE_LINE if has_project else NOT_AWARE_NO_PROJECT_LINE
    else:
        line = BUILD_FAILED_LINE if has_project else BUILD_FAILED_NO_PROJECT_LINE
    # With no [project] table, the Hatchling fallback attempt is guaranteed
    # to fail (its WheelBuilder requires one), as _skip_hatchling_fallback
    # decides for a registered backend: skip it rather than raise a
    # Hatchling-branded error for a project that has nothing to do with it.
    warn_discovery(log, line, dir=project_dir, backend=backend)
    if _uv_overrides_unseen(backend, pyproject_data, allow_build=build is not None):
        warn_discovery(log, UV_OVERRIDES_LINE, dir=project_dir)
    if not has_project:
        return [], _noop_cleanup
    return None


def _discover_with_registered_backend(
    backend: str,
    registered: _RegisteredBackend,
    project_dir: Path,
    pyproject_data: dict[str, object] | None,
    *,
    build: BuildSettings | None,
) -> tuple[list[IncludedFile], Callable[[], None]] | None:
    """*backend* has its own static discovery module -- try that first,
    then (with *build* given, i.e. ``--allow-build``) a real build as a
    robustness fallback for when the static discoverer gives up, before
    finally deferring to the Hatchling heuristic.

    Returns a result to return immediately, or ``None`` to fall through
    to the Hatchling heuristic."""
    # A "writer" backend (registered.needs_write_lock, see
    # _RegisteredBackend) process-wide os.chdir()s for the duration of
    # its call and needs _DISCOVERY_LOCK's exclusive write mode -- see
    # the lock's own docstring. Every other backend is a "reader" and
    # only needs to be kept out of a concurrent writer's chdir window,
    # not out of each other's way.
    lock_ctx = (
        _DISCOVERY_LOCK.write()
        if registered.needs_write_lock
        else _DISCOVERY_LOCK.read()
    )
    take_discovery_failure()
    with lock_ctx:
        files = registered.discoverer(project_dir, pyproject_data=pyproject_data)
    if files is not None:
        return files, _noop_cleanup
    failed = take_discovery_failure()
    # The registered backend's own static discoverer gave up. This is
    # the "robustness fallback for Track A" of the build-and-read
    # mechanism (non-hatchling-file-discovery.md): ANY registered backend
    # (setuptools, poetry, pdm, flit) gets it with no backend-specific
    # wiring, because build_and_read_wheel() does not care which backend
    # it is. Must never be reached when the static
    # discoverer already succeeded above (that returns immediately) -- a
    # real build must never run when the fast, safe static rescan
    # already worked.
    if build is not None:
        build_result = _try_build_and_read(
            backend,
            project_dir,
            build=build,
            static_failed=True,
        )
        if build_result is not None:
            return build_result
    if _skip_hatchling_fallback(backend, pyproject_data, project_dir, failed=failed):
        return [], _noop_cleanup
    return None


def _discover_included_files(
    project_dir: Path,
    *,
    assume_backend: str | None = None,
    build: BuildSettings | None = None,
) -> tuple[list[IncludedFile], Callable[[], None]]:
    """Resolve the wheel's file list via the project's build backend.

    Any backend other than Hatchling that doesn't have a dedicated
    discovery module (or whose static config can't be resolved) falls
    back to the Hatchling-based heuristic, with a ``WARNING:`` since
    the result may not accurately reflect that backend's actual
    inclusion rules -- unless *build* (not ``None`` ⇔ ``--allow-build``)
    opts into a real PEP 517 build instead (see
    :mod:`pitloom.core._models_wheel_build_and_read`), which is tried
    first in both of those cases (no dedicated module at all, or a
    dedicated module whose own static discovery failed) before falling
    back to Hatchling.

    Returns the resolved files plus a cleanup callback the caller MUST
    invoke once done consuming the files' ``.path`` values -- a no-op
    for every path except a successful build-and-read, whose real files
    live in a temp directory the callback removes.

    *assume_backend*, when given, skips reading ``pyproject.toml`` and
    detecting the backend entirely and dispatches straight to that
    backend -- for callers that already know it by construction (e.g.
    the Hatchling build hook, which is definitionally always Hatchling).
    """
    # pylint: disable=import-outside-toplevel
    from pitloom.core._models_wheel_flit import discover as discover_flit
    from pitloom.core._models_wheel_pdm import discover as discover_pdm
    from pitloom.core._models_wheel_poetry import discover as discover_poetry
    from pitloom.core._models_wheel_setuptools import discover as discover_setuptools
    from pitloom.extract.project.setuptools import (
        detect_build_backend,
        read_pyproject_toml,
    )

    # needs_write_lock (2nd tuple element) states, right where each
    # backend is registered, whether its discover() process-wide
    # os.chdir()s and therefore needs _DISCOVERY_LOCK's exclusive write
    # mode (see the lock's own docstring) -- a required field, not a
    # separately-maintained allowlist elsewhere in this file, so
    # registering a new backend can't silently default to "reader"
    # without the registerer making the choice explicit right here.
    # PDM-backend needs it because its own package auto-discovery
    # (``pdm.backend.base._find_top_packages``) globs relative to the
    # process cwd, not the ``Builder``'s ``location`` -- see
    # :mod:`pitloom.core._models_wheel_pdm`. Poetry and Flit don't chdir.
    backend_discoverers: dict[str, _RegisteredBackend] = {
        "setuptools": _RegisteredBackend(discover_setuptools, needs_write_lock=True),
        "poetry": _RegisteredBackend(discover_poetry, needs_write_lock=False),
        "flit": _RegisteredBackend(discover_flit, needs_write_lock=False),
        "pdm": _RegisteredBackend(discover_pdm, needs_write_lock=True),
    }

    pyproject_data: dict[str, object] | None
    if assume_backend is not None:
        backend: str | None = assume_backend
        pyproject_data = None
    else:
        # Parsed once and reused for backend detection and setuptools' own
        # static-config check below -- both read the same pyproject.toml.
        pyproject_data = read_pyproject_toml(project_dir)
        backend = detect_build_backend(project_dir, pyproject_data=pyproject_data)

    if backend not in (None, "hatchling"):
        registered = backend_discoverers.get(backend)
        result = (
            _discover_with_no_static_module(
                backend,
                project_dir,
                pyproject_data,
                build=build,
            )
            if registered is None
            else _discover_with_registered_backend(
                backend,
                registered,
                project_dir,
                pyproject_data,
                build=build,
            )
        )
        if result is not None:
            return result

    # Hatchling's discover() never touches cwd (project_dir is always
    # already absolute here -- see get_wheel_files), so concurrent
    # Hatchling calls only need to be kept out of a concurrent writer's
    # chdir window, never out of each other's way.
    with _DISCOVERY_LOCK.read():
        return _models_wheel_hatchling.discover(project_dir) or [], _noop_cleanup
