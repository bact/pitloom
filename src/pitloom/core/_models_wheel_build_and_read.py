# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generic, backend-agnostic PEP 517 build-and-read file discovery.

Actually invokes whatever build hooks the target project's own
``pyproject.toml`` declares to produce a real wheel, then reads that
wheel's own file list -- for a backend with no static-config discovery
module of its own (e.g. ``uv_build``, a thin PEP 517 shim with no
in-process introspection API), or as a fallback when a backend that
*does* have one fails to resolve on a given project. This mechanism
never needs to know a backend's name -- it just runs the project's
declared PEP 517 hooks via ``python -m build``, whatever they are -- see
:mod:`pitloom.core._models_wheel_dispatch`'s ``_try_build_and_read``, the
sole caller.

The build itself runs as a child *process tree* (see
:mod:`pitloom.core._models_wheel_build_subprocess`), not in-process --
a thread can't be killed, and PyPA ``build``'s own hooks don't cover
everything a build backend can do (e.g. spawn its own subprocesses),
so a hung or misbehaving build can only be bounded and terminated by
running it out-of-process with a real ``--build-timeout``.

Gated everywhere it's called from behind ``--allow-build``: this is the
first mechanism in Pitloom that executes third-party build-time code.
Every other backend discovery module deliberately avoids this (Flit's
AST-only version scan, PDM's ``WheelBuilder``/``Context``-not-``.build()``
avoidance).

See also: ``working-docs/design/non-hatchling-file-discovery.md``
(Track A/B split, "build-and-read" as roadmap item #4) and
``working-docs/implementation/allow-build-timeout.md`` (subprocess
design, traps, rejected paths).
"""

from __future__ import annotations

import functools
import logging
import shutil
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path

from pitloom.core._models_wheel_build_subprocess import (
    BuildTimeoutError,
    run_build_subprocess,
)
from pitloom.core._models_wheel_types import (
    BUILD_LOG_PREFIX,
    IncludedFile,
    is_dist_info_path,
)
from pitloom.core.archive_member_names import zip_file_members
from pitloom.core.build_signals import BUILD_ACTIVITY, TerminationGuard
from pitloom.core.temp_dirs import (
    one_shot,
    registered_temp_dir,
    rmtree_quietly,
    warn_if_left_behind,
)
from pitloom.logging_config import one_line

log = logging.getLogger(__name__)


def _extract_wheel_to_included_files(
    wheel_path: Path, extract_dir: Path
) -> list[IncludedFile]:
    """Extract *wheel_path*'s real, non-``.dist-info`` entries into
    *extract_dir*, returning ordinary :class:`IncludedFile` pairs -- the
    same shape every static discoverer already produces, so the shared
    per-file loop in :mod:`pitloom.core._models_wheel` (hashing,
    header/content-type scanning) needs no special-casing for this
    mechanism.

    ``.dist-info/*`` is excluded: every other backend's ``IncludedFile``
    list holds pre-build *source* files only, and ``.dist-info`` is a
    build-generated artifact with no source-stage equivalent. It is not
    payload and no SBOM lists it (see
    :func:`pitloom.extract.wheel.payload_files`).

    Entry names go through
    :func:`~pitloom.core.archive_member_names.zip_file_members`, the same
    normaliser :func:`pitloom.extract.wheel.read_wheel` uses, so names match
    across both readers on every OS. ``target`` is composed via
    :class:`~pathlib.Path`'s own ``/`` operator, never string concatenation.

    Zip-slip guard: unlike every static discoverer (which only ever
    walks real files already inside *project_dir*), this one writes
    bytes to disk from a zip archive a real, external build process
    just produced. ``zip_file_members`` already skips ``../``-containing
    and absolute entry names; the ``resolve()`` check below is defence in
    depth, so no entry can overwrite a file outside *extract_dir*.
    """
    resolved_extract_dir = extract_dir.resolve()
    files: list[IncludedFile] = []
    with zipfile.ZipFile(wheel_path) as zf:
        for distribution_path, info in zip_file_members(
            zf, wheel_path.name, log, BUILD_LOG_PREFIX
        ):
            if is_dist_info_path(distribution_path):
                continue
            target = extract_dir / distribution_path
            if not target.resolve().is_relative_to(resolved_extract_dir):
                log.warning(
                    "%sARCHIVE=%r ENTRY=%r: resolves outside "
                    "the extraction directory -- skipped, not written to disk",
                    BUILD_LOG_PREFIX,
                    wheel_path.name,
                    info.orig_filename,
                )
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            files.append(
                IncludedFile(path=str(target), distribution_path=distribution_path)
            )
    return files


def build_and_read_wheel(
    project_dir: Path, *, isolated: bool = True, timeout: int
) -> tuple[list[IncludedFile], Callable[[], None]] | None:
    """Build a real wheel for *project_dir* and return its non-``.dist-info``
    files as on-disk :class:`IncludedFile` entries, plus a cleanup callback
    the caller MUST invoke once done (it deletes the extraction directory
    backing ``.path``).

    *timeout* (seconds) is required, so a call site that forgets to thread
    it through fails with a ``TypeError`` rather than using some default.

    Returns ``None``, with a ``WARNING:``, on any failure -- including a
    timeout (its own ``WARNING:``) and a wheel with no non-``.dist-info``
    file -- the same "``None`` means fall back" contract as every static
    discoverer.

    Both temp directories are registered with a
    :class:`~pitloom.core.build_signals.TerminationGuard` as soon as they
    exist and removed on every exit path; the extraction directory survives
    only a successful return, protected while the caller's outermost guard
    is held. A directory not fully removed (e.g. a file still open on
    Windows) gets a ``WARNING:``. Signal behaviour: see
    :mod:`pitloom.core.build_signals`; the Ctrl-C window between a
    directory's creation and its registration is a documented limitation.
    """
    with TerminationGuard() as termination:
        return _build_and_read_wheel(
            project_dir, isolated=isolated, timeout=timeout, termination=termination
        )


def _build_and_read_wheel(
    project_dir: Path, *, isolated: bool, timeout: int, termination: TerminationGuard
) -> tuple[list[IncludedFile], Callable[[], None]] | None:
    """:func:`build_and_read_wheel` inside its :class:`TerminationGuard`."""
    remove_work_dir = remove_extract_dir = _nothing_to_remove
    handed_over = False
    try:
        with termination.hold(BUILD_ACTIVITY):
            extract_dir, remove_extract_dir = registered_temp_dir(
                termination, "pitloom-build-and-read-", log_prefix=BUILD_LOG_PREFIX
            )
            work_dir, remove_work_dir = _registered_work_dir(termination)
            wheel_path = run_build_subprocess(
                project_dir,
                work_dir,
                isolated=isolated,
                timeout=timeout,
                termination=termination,
            )
        # Not held: a signal during a long extraction must not wait for it.
        files = _extract_wheel_to_included_files(wheel_path, extract_dir)
        if not files:
            log.warning(
                "%s%s's real build produced a wheel with "
                "no non-.dist-info files -- treating as a discovery "
                "failure, not an authoritative empty result",
                BUILD_LOG_PREFIX,
                project_dir,
            )
            return None
        handed_over = True
        return files, remove_extract_dir
    except BuildTimeoutError as exc:
        log.warning(
            "%sbuild-and-read for %s timed out after %ds (--build-timeout) -- %s",
            BUILD_LOG_PREFIX,
            project_dir,
            exc.timeout,
            "build process tree terminated"
            if exc.tree_terminated
            else "could not confirm the build process tree terminated",
        )
        return None
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log.warning(
            "%sbuild-and-read discovery failed for %s: %s",
            BUILD_LOG_PREFIX,
            project_dir,
            one_line(exc),
        )
        return None
    finally:
        try:
            remove_work_dir()
        finally:
            if not handed_over:
                remove_extract_dir()


def _registered_work_dir(
    termination: TerminationGuard,
) -> tuple[Path, Callable[[], None]]:
    """The build's new work directory and its removal, registered with
    *termination*. Call inside a hold, so no termination signal acts in
    between (a Ctrl-C still can)."""
    # Not a with-block: its removal must be the registered callback.
    # ignore_cleanup_errors: on Windows a just-killed process may still
    # hold a handle; a leftover is reported instead of raising.
    # pylint: disable-next=consider-using-with
    work = tempfile.TemporaryDirectory(prefix="plb-", ignore_cleanup_errors=True)
    remove = one_shot(functools.partial(_remove_work_dir, work))
    termination.add_cleanup(remove)
    return Path(work.name), remove


def _nothing_to_remove() -> None:
    """Stands in for a removal until its directory exists."""


def _remove_work_dir(work: tempfile.TemporaryDirectory[str]) -> None:
    """Remove the build's work directory, with a ``WARNING:`` if anything
    survives. :meth:`~tempfile.TemporaryDirectory.cleanup` repeats a
    removal cut short, and resets read-only permissions on the way."""
    try:
        work.cleanup()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Python 3.10's cleanup() ends in RecursionError when an rmdir
        # fails (e.g. a directory still in use on Windows); a cleanup
        # callback must not raise.
        log.debug("%swork directory cleanup failed: %r", BUILD_LOG_PREFIX, exc)
        rmtree_quietly(Path(work.name), BUILD_LOG_PREFIX)
    warn_if_left_behind(Path(work.name), BUILD_LOG_PREFIX)
