# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Temporary directories whose removal is registered with a
:class:`~pitloom.core.build_signals.TerminationGuard`, the directory a
remote source is fetched into (:func:`temp_dir`), and the removal both use,
which never raises (:func:`remove_temp_dir`). Each takes the frame of the
surface that made the directory (:data:`pitloom.messages.BUILD_FRAME`,
``GIT_FRAME``, ...), which comes before its ``temp-dir-unwritable`` line,
and refuses one that does not allow that line on entry (a caller that
removes later calls :func:`check_frame` first): a cleanup runs where an
error is lost (a signal handler, a ``weakref.finalize`` at exit).

See also: :mod:`pitloom.core.build_signals` (the guard, signal
behaviour), :mod:`pitloom.core._models_wheel_build_and_read` (the
build-and-read caller), :mod:`pitloom.extract.remote.git` and
:mod:`pitloom.extract.remote.pypi` (the remote sources).
"""

from __future__ import annotations

import functools
import logging
import os
import shutil
import stat
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from os import lstat
from pathlib import Path

from pitloom.core.build_signals import TerminationGuard
from pitloom.core.quote_source import quote_source
from pitloom.core.url_masking import mask_checkout
from pitloom.messages import Frame, emit
from pitloom.messages.build import TEMP_DIR_UNWRITABLE, require_codes

log = logging.getLogger(__name__)


def rmtree(path: Path | str, *, ignore_errors: bool = False) -> None:
    """``shutil.rmtree``, looked up when called: the removal every temporary
    directory of Pitloom's goes through, which a test makes fail here, not
    on :mod:`shutil` (which every thread shares)."""
    shutil.rmtree(path, ignore_errors=ignore_errors)


def registered_temp_dir(
    termination: TerminationGuard, prefix: str, *, frame: Frame
) -> tuple[Path, Callable[[], None]]:
    """A new temporary directory named with *prefix* and its removal,
    registered with *termination*. Call inside a hold, so no termination
    signal acts in between (a Ctrl-C still can).

    *frame* comes before the removal's messages.

    Raises:
        pitloom.core.internal_error.InternalError: *frame* does not allow
            the ``temp-dir-unwritable`` line (:func:`check_frame`).
    """
    check_frame(frame)
    path = Path(tempfile.mkdtemp(prefix=prefix))
    remove = one_shot(functools.partial(remove_temp_dir, path, frame=frame))
    termination.add_cleanup(remove)
    return path, remove


@contextmanager
def temp_dir(prefix: str, *, frame: Frame) -> Iterator[Path]:
    """A new temporary directory named with *prefix* (``mkdtemp``'s eight
    random characters after it), removed on exit by :func:`remove_temp_dir`:
    one that cannot be fully removed (a file still held open on Windows) is
    left behind with one ``WARNING:`` after *frame*, never an error, so a
    caller that wrote its output inside the block keeps it.

    No termination guard: Ctrl-C removes it, a process ended by SIGTERM or
    SIGKILL leaves it (:func:`registered_temp_dir` is the guarded one).

    Raises:
        pitloom.core.internal_error.InternalError: *frame* does not allow
            the ``temp-dir-unwritable`` line (:func:`check_frame`), before
            the directory is made.
    """
    check_frame(frame)
    path = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield path
    finally:
        remove_temp_dir(path, frame=frame)


def check_frame(frame: Frame) -> None:
    """Refuse *frame* unless the ``temp-dir-unwritable`` line may follow it.

    Raises:
        pitloom.core.internal_error.InternalError: It may not, or it takes
            values.
    """
    require_codes(frame, TEMP_DIR_UNWRITABLE.code)


def one_shot(remove: Callable[[], None]) -> Callable[[], None]:
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


def remove_temp_dir(path: Path | str, *, frame: Frame) -> None:
    """Remove *path*, with a ``WARNING:`` (after *frame*) if anything
    survives. Never raises, but for a *frame* that does not allow that line
    (:func:`check_frame`), checked first."""
    check_frame(frame)
    rmtree_quietly(Path(path), frame=frame)
    warn_if_left_behind(Path(path), frame=frame)


def rmtree_quietly(path: Path, *, frame: Frame) -> None:
    """``shutil.rmtree(path, ignore_errors=True)``, once more after what is
    left is made writable (:func:`_make_writable`; a read-only file, such as
    a Git pack file on Windows, is not removed otherwise, as
    :class:`tempfile.TemporaryDirectory` knows). Never raises: rmtree still
    raises ``RecursionError`` on a tree deeper than the recursion limit
    (Python 3.10's rmtree recurses; the directory's creator controls its
    depth). *frame* comes before its ``DEBUG`` line (:func:`check_frame`
    is the caller's)."""
    try:
        rmtree(path, ignore_errors=True)
        if os.path.isdir(path) and not _is_link(str(path)):
            _make_writable(path)
            rmtree(path, ignore_errors=True)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log.debug(
            "%sremoving %s failed: %r",
            frame.render({}),
            quote_source(path.name),
            exc,
        )


def _make_writable(path: Path) -> None:
    """Give *path* and every directory below it owner read, write and search
    permission, and every file owner read and write permission; a symbolic
    link or a Windows junction (:func:`_is_link`) is left alone and not
    descended into (``chmod`` would change its target, which may be
    outside). Top-down, so a directory is opened once it can be. Each
    failure is passed over."""
    with suppress(OSError):
        os.chmod(path, 0o700)
    for here, folders, files in os.walk(path, followlinks=False):
        # A junction is no symbolic link to os.walk (before Python 3.12 it
        # descends into one): pruned here, top-down.
        folders[:] = [n for n in folders if not _is_link(os.path.join(here, n))]
        for names, mode in ((folders, 0o700), (files, 0o600)):
            for name in names:
                entry = os.path.join(here, name)
                if not _is_link(entry):
                    with suppress(OSError):
                        os.chmod(entry, mode)


def _is_link(entry: str) -> bool:
    """Whether *entry* is a symbolic link, or any other reparse point (a
    junction) on Windows, or cannot be looked at: one to leave alone."""
    try:
        info = lstat(entry)
    except OSError:
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(
        attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def warn_if_left_behind(path: Path, *, frame: Frame) -> None:
    """``WARNING:`` (``temp-dir-unwritable``, after *frame*) when a temp
    directory survived its removal.

    Names the directory, not its path: it is in the system temp directory
    (``mkdtemp``'s default), and a full path is a machine-specific string
    in a log. A Git checkout or a PyPI or Hugging Face download directory
    is named by its placeholder (``<checkout>``, ``<download>``,
    :func:`~pitloom.core.url_masking.mask_checkout`) in the record itself,
    so a library caller's log holds no random name either.

    Raises:
        pitloom.core.internal_error.InternalError: *frame* does not allow
            the line (:func:`check_frame`), checked first.
    """
    check_frame(frame)
    # os.path.lexists, not Path.exists(): never raises (e.g. EACCES).
    if os.path.lexists(path):
        # Masked before the field escapes it (as quote_source masked it).
        name = mask_checkout(path.name)
        emit(log, TEMP_DIR_UNWRITABLE, logging.WARNING, frame=frame, dir=name)
