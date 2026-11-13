# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a file discovery runs within: the project directory as the working
directory for a backend that resolves paths from it
(:func:`discovery_chdir`), and, in a Git URL's clone, a wall-clock cap
(:func:`discovery_deadline`).

In a clone the import path holds neither the working directory (``''``,
``'.'``, a relative entry: a library caller's ``python -c``, a REPL, a
notebook) nor the clone while the working directory is the clone: a module
setuptools or a plugin imports lazily (``Cython``, ``dl``), or an entry
point a ``*.dist-info`` of the clone declares, would be the repository's
code. Out of a clone nothing changes.

The cap is checked cooperatively, at each function call of the
discovering thread (a profile hook of that thread alone, so a call blocked
in C is not stopped): past :data:`DISCOVERY_SECONDS` it raises
:class:`_Expired`, which leaves the discovery as
:class:`~pitloom.core._models_wheel_types.DiscoveryTimeoutError` after one
``over-cap`` ``WARNING:``; the discovery's caller falls back. Two folder
links to ``.`` would make a walk endless; a clone drops every folder link
(:func:`pitloom.extract.remote.git.fetch_git_project`), so the cap is the
second guard. (An exception raised into the thread from a timer, with
``PyThreadState_SetAsyncExc``, escapes ``try`` blocks on Python 3.13.)

See also: :mod:`pitloom.core._models_wheel_setuptools` and
:mod:`pitloom.core._models_wheel_pdm` (the backends that chdir),
:mod:`pitloom.core._models_wheel_clone` (what a clone leaves out).
"""

from __future__ import annotations

import gc
import importlib
import logging
import math
import os
import sys
import time
import warnings
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from pathlib import Path, PurePath
from traceback import clear_frames
from types import FrameType, TracebackType

from pitloom.core._models_wheel_clone import clone_root
from pitloom.core._models_wheel_types import DiscoveryTimeoutError
from pitloom.core.clone_mark import in_remote_clone
from pitloom.core.path_confine import is_inside
from pitloom.messages.files import (
    OVER_CAP,
    Cap,
    warn_over_cap,
)

log = logging.getLogger(__name__)

#: Seconds a file discovery may take in a Git URL's clone.
DISCOVERY_SECONDS = 60.0


class _Expired(BaseException):
    """Raised in the discovering thread when :data:`DISCOVERY_SECONDS` have
    passed: a ``BaseException``, so no ``except Exception`` of a backend
    swallows it."""


@contextmanager
def discovery_chdir(project_dir: Path) -> Iterator[None]:
    """Run the block from *project_dir* as the working directory (a
    process-wide ``os.chdir()``, safe only under the discovery dispatcher's
    exclusive write lock), restored on exit; in a clone, with the
    working directory and the clone off the import path
    (:func:`_off_import_path`)."""
    original_cwd = Path.cwd()
    os.chdir(project_dir)
    try:
        if in_remote_clone():
            with _off_import_path(project_dir):
                yield
        else:
            yield
    finally:
        os.chdir(original_cwd)


@contextmanager
def _off_import_path(project_dir: Path) -> Iterator[None]:
    """``sys.path`` without its relative entries (``''`` and ``'.'``
    included) and those in the clone of *project_dir*, restored on exit;
    the import system's caches are dropped on entry and on exit."""
    saved = list(sys.path)
    root = clone_root(project_dir)
    sys.path[:] = [entry for entry in saved if _kept_entry(entry, root)]
    importlib.invalidate_caches()
    try:
        yield
    finally:
        sys.path[:] = saved
        importlib.invalidate_caches()


def _kept_entry(entry: object, root: PurePath) -> bool:
    """Whether the ``sys.path`` *entry* is an absolute path out of the clone
    at *root*."""
    if not isinstance(entry, (str, os.PathLike)):
        return False
    path = os.fspath(entry)
    # A NUL is checked first: Windows' realpath does not raise for one.
    if not isinstance(path, str) or "\0" in path or not os.path.isabs(path):
        return False
    try:
        return not is_inside(PurePath(os.path.realpath(path)), root)
    except (OSError, ValueError):  # a NUL, or a link loop on Windows
        return False


def discovery_deadline(project_dir: Path) -> AbstractContextManager[None]:
    """In a Git URL's clone, a block stopped past :data:`DISCOVERY_SECONDS`
    with one ``over-cap`` ``WARNING:`` naming *project_dir* and
    :class:`~pitloom.core._models_wheel_types.DiscoveryTimeoutError`
    (:class:`_Deadline`); out of a clone, or while a profiler watches the
    thread (its hook is left in place), no cap."""
    if not in_remote_clone() or sys.getprofile() is not None:
        return nullcontext()
    return _Deadline(project_dir)


class _Deadline:
    """A cap on the wall-clock time of the block, checked cooperatively by a
    profile hook of this thread (``sys.setprofile``) at each function call:
    past it, :class:`_Expired` is raised in the block, once (the hook is
    then off), and leaves it as
    :class:`~pitloom.core._models_wheel_types.DiscoveryTimeoutError`. The
    hook never raises in :meth:`__exit__`, so the block's end is never cut
    short."""

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = project_dir
        self._until = 0.0

    def __enter__(self) -> None:
        self._until = time.monotonic() + DISCOVERY_SECONDS
        sys.setprofile(self._check)

    def _check(self, frame: FrameType, event: str, _arg: object) -> None:
        if (
            event in _CALLS
            and frame.f_code is not _EXIT_CODE
            and time.monotonic() > self._until
        ):
            raise _Expired

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Remove the hook; say a cap passed, and raise for it.

        Raises:
            pitloom.core._models_wheel_types.DiscoveryTimeoutError: The cap
                passed.
        """
        sys.setprofile(None)
        if isinstance(exc, _Expired):
            # What the stopped walk held open (a scandir iterator) is let go
            # here, quietly, not when the error is dropped or collected.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                clear_frames(traceback)
                exc.__traceback__ = None
                gc.collect()
            warn_over_cap(
                log,
                Cap(math.ceil(DISCOVERY_SECONDS), "second", "file-discovery", "DIR"),
                str(self._project_dir),
                "file list not read",
            )
            raise DiscoveryTimeoutError(
                DISCOVERY_SECONDS, pitloom_code=OVER_CAP.code
            ) from None


#: The profile events the cap is checked at: a call, of Python or C.
_CALLS = frozenset({"call", "c_call"})
#: The code of :meth:`_Deadline.__exit__`, which the hook never stops.
_EXIT_CODE = _Deadline.__exit__.__code__
