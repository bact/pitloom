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
import os
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
    to_posix_distribution_path,
)
from pitloom.core.build_signals import TerminationGuard

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

    ``.dist-info/*`` is excluded even though it's genuinely present in
    this real, already-built wheel -- every other backend's
    ``IncludedFile`` list represents pre-build *source* files only, and
    ``.dist-info`` is a build-generated artifact with no source-stage
    equivalent (see CLAUDE.md's "stage-scoped helpers" principle);
    including it here would make this mechanism's Source-SBOM file list
    diverge in kind from every other backend's for no benefit --
    ``embed-wheel``'s own ``_merge_file_extras`` already gets
    ``.dist-info`` entries from ``read_wheel()`` directly, so nothing is
    lost.

    A wheel's own internal entries are always ``/``-separated per the ZIP
    spec (so ``to_posix_distribution_path()`` is a safety net here, not a
    live bug on any platform), but ``target`` (a real, on-disk path) is
    composed via :class:`~pathlib.Path`'s own ``/`` operator, which
    accepts a ``/``-separated string as multiple path components on
    every platform including Windows -- never raw string concatenation.

    Zip-slip guard: unlike every static discoverer (which only ever
    walks real files already inside *project_dir*), this one writes
    bytes to disk from a zip archive a real, external build process
    just produced -- a ``../``-containing or absolute entry name (from
    a buggy or malicious build backend) must never be allowed to
    resolve outside *extract_dir* and overwrite an unrelated file
    elsewhere on the filesystem.
    """
    resolved_extract_dir = extract_dir.resolve()
    files: list[IncludedFile] = []
    with zipfile.ZipFile(wheel_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            distribution_path = to_posix_distribution_path(info.filename)
            if is_dist_info_path(distribution_path):
                continue
            target = extract_dir / distribution_path
            if not target.resolve().is_relative_to(resolved_extract_dir):
                log.warning(
                    "%s%s: wheel entry %r resolves outside "
                    "the extraction directory -- skipped, not written to disk",
                    BUILD_LOG_PREFIX,
                    wheel_path,
                    distribution_path,
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
    """Build a real wheel for *project_dir* and return its file list as
    ordinary, on-disk :class:`IncludedFile` entries, plus a cleanup
    callback the caller MUST invoke once done consuming them (deletes the
    temp extraction directory backing ``.path``).

    *timeout* is a required keyword (seconds) -- resolved once upstream
    via :func:`~pitloom.core._models_wheel_types.resolve_build_timeout`,
    so a call site that forgets to thread it through fails loudly with a
    ``TypeError`` instead of silently reusing some default here. Passed
    straight to
    :func:`~pitloom.core._models_wheel_build_subprocess.run_build_subprocess`,
    which runs the build as its own child process tree and terminates it
    if *timeout* elapses.

    Returns ``None`` on any failure (backend not installable, network
    unavailable under isolation, the build script itself fails, the
    build timed out, or the build produced a wheel with zero
    non-``.dist-info`` files) -- same "``None`` means fall back" contract
    as every static discoverer, logged with a ``WARNING:`` here (the
    caller's own fallback-to-Hatchling warning fires on top of this one,
    same two-tier pattern setuptools'/PDM's/Flit's own failure paths
    already have). A timeout gets its own, more specific ``WARNING:``
    naming the elapsed duration, checked before the generic failure
    ``except``.

    Removes both temp directories on every exit path, including
    ``KeyboardInterrupt`` and SIGTERM/SIGHUP/SIGBREAK: each one's removal
    is registered with the :class:`~pitloom.core.build_signals.TerminationGuard`
    as soon as it exists, the build's own work directory is removed once
    the wheel is extracted, and the *extraction* directory (whose contents
    are what the returned ``IncludedFile.path`` values point at) unless the
    call actually succeeded -- only then does it survive past this
    function's return, via the returned cleanup callback. A directory that
    could not be fully removed gets a ``WARNING:`` naming it.

    A termination signal is held only while the directories are created
    and the build runs: it stops the build (kill tree, reap), then both
    directories are removed and the signal re-raised. From the build's
    exit on -- extracting a possibly multi-GiB wheel, removing the work
    directory -- the signal handler removes both directories and ends the
    process at once. After a successful return, the extraction directory
    stays protected for as long as the caller's own
    :class:`~pitloom.core.build_signals.TerminationGuard` (the outermost
    one entered) is held; with none, until this returns.
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
        with termination.hold():
            extract_dir, remove_extract_dir = _registered_extract_dir(termination)
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
            exc,
        )
        return None
    finally:
        remove_work_dir()
        if not handed_over:
            remove_extract_dir()


def _registered_extract_dir(
    termination: TerminationGuard,
) -> tuple[Path, Callable[[], None]]:
    """A new extraction directory and its removal, registered with
    *termination*. Call inside a hold, so no signal acts in between."""
    path = Path(tempfile.mkdtemp(prefix="pitloom-build-and-read-"))
    remove = _one_shot(functools.partial(_remove_temp_dir, path))
    termination.add_cleanup(remove)
    return path, remove


def _registered_work_dir(
    termination: TerminationGuard,
) -> tuple[Path, Callable[[], None]]:
    """The build's new work directory and its removal, registered with
    *termination*. Call inside a hold, so no signal acts in between."""
    # Not a with-block: its removal must be the registered callback.
    # ignore_cleanup_errors: on Windows a just-killed process may still
    # hold a handle; a leftover is reported instead of raising.
    # pylint: disable-next=consider-using-with
    work = tempfile.TemporaryDirectory(prefix="plb-", ignore_cleanup_errors=True)
    remove = _one_shot(functools.partial(_remove_work_dir, work))
    termination.add_cleanup(remove)
    return Path(work.name), remove


def _nothing_to_remove() -> None:
    """Stands in for a removal until its directory exists."""


def _one_shot(remove: Callable[[], None]) -> Callable[[], None]:
    """*remove* (a temp directory's removal) as a cleanup callback that
    runs it to completion once.

    Idempotent, as
    :meth:`~pitloom.core.build_signals.TerminationGuard.add_cleanup`
    requires -- both the caller and the guard may run it. Marked done only
    after *remove* returns, so a run cut short by the signal handler is
    repeated by the handler's own run.
    """
    done = False

    def cleanup() -> None:
        nonlocal done
        if not done:
            remove()
            done = True

    return cleanup


def _remove_work_dir(work: tempfile.TemporaryDirectory[str]) -> None:
    """Remove the build's work directory, with a ``WARNING:`` if anything
    survives. :meth:`~tempfile.TemporaryDirectory.cleanup` repeats a
    removal cut short, and resets read-only permissions on the way."""
    work.cleanup()
    _warn_if_left_behind(Path(work.name))


def _remove_temp_dir(path: Path) -> None:
    """Remove *path*, with a ``WARNING:`` if anything survives."""
    shutil.rmtree(path, ignore_errors=True)
    _warn_if_left_behind(path)


def _warn_if_left_behind(path: Path) -> None:
    """``WARNING:`` when a temp directory survived its removal."""
    # os.path.lexists, not Path.exists(): never raises (e.g. EACCES).
    if os.path.lexists(path):
        log.warning(
            "%scould not fully remove temporary directory %s", BUILD_LOG_PREFIX, path
        )
