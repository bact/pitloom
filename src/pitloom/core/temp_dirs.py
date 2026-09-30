# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Temporary directories whose removal is registered with a
:class:`~pitloom.core.build_signals.TerminationGuard`.

See also: :mod:`pitloom.core.build_signals` (the guard, signal
behaviour) and :mod:`pitloom.core._models_wheel_build_and_read` (the
build-and-read caller).
"""

from __future__ import annotations

import functools
import logging
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from pitloom.core.build_signals import TerminationGuard

log = logging.getLogger(__name__)


def registered_temp_dir(
    termination: TerminationGuard, prefix: str, *, log_prefix: str
) -> tuple[Path, Callable[[], None]]:
    """A new temporary directory named with *prefix* and its removal,
    registered with *termination*. Call inside a hold, so no termination
    signal acts in between (a Ctrl-C still can).

    *log_prefix* (e.g. ``"Build: "``) starts the removal's log messages.
    """
    path = Path(tempfile.mkdtemp(prefix=prefix))
    remove = one_shot(functools.partial(_remove_temp_dir, path, log_prefix))
    termination.add_cleanup(remove)
    return path, remove


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


def _remove_temp_dir(path: Path, log_prefix: str) -> None:
    """Remove *path*, with a ``WARNING:`` if anything survives."""
    rmtree_quietly(path, log_prefix)
    warn_if_left_behind(path, log_prefix)


def rmtree_quietly(path: Path, log_prefix: str) -> None:
    """``shutil.rmtree(path, ignore_errors=True)``, which still raises
    ``RecursionError`` on a tree deeper than the recursion limit (Python
    3.10's rmtree recurses; the directory's creator controls its depth)."""
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log.debug("%sremoving %s failed: %r", log_prefix, path, exc)


def warn_if_left_behind(path: Path, log_prefix: str) -> None:
    """``WARNING:`` when a temp directory survived its removal."""
    # os.path.lexists, not Path.exists(): never raises (e.g. EACCES).
    if os.path.lexists(path):
        log.warning("%scould not fully remove temporary directory %s", log_prefix, path)
