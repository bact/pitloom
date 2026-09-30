# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Warn about project directories that file discovery could not list.

Every backend's discovery delegates its directory walk to the backend's
own library: Hatchling's ``safe_walk()`` and flit-core's, pdm-backend's
and setuptools' ``os.walk()``, plus ``glob``/``Path.glob()`` (pdm-backend,
poetry-core, setuptools). None of them takes an ``onerror``, and ``glob``
swallows ``OSError`` itself, so a directory that cannot be listed drops
its whole subtree with nothing said.

:func:`warn_unlistable_dirs` records, through a PEP 578 audit hook, every
directory the block asks ``os.scandir()``/``os.listdir()`` to list in the
current context. When the block ends, each recorded directory under the
project is opened again, and one ``WARNING:`` is logged for each that
fails for a reason other than absence (per
:func:`~pitloom.core.path_probe.is_missing_errno`). The warning names only
directories the backend tried to list. A backend that prunes before
listing (Hatchling) never lists a directory its rules exclude; one that
globs first and filters after (poetry-core, pdm-backend, setuptools'
``package_data``) does, so an excluded directory can still be named even
though no file under it would have been included. The wording therefore
says only that the listing failed, not that files are missing.

The hook is installed once per process on first use and cannot be
removed. Outside the block it returns after one set-membership test and
one context-variable lookup.

A real build (``--allow-build``) walks in a child process the hook
cannot see.

See also: :mod:`pitloom.core._models_wheel` (the caller),
:mod:`pitloom.core.path_probe` (shared classification and wording).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path, PurePath

from pitloom.core.path_probe import UNLISTABLE_DIR_WARNING, is_missing_errno

__all__ = ["warn_unlistable_dirs"]

log = logging.getLogger(__name__)

_LISTING_EVENTS = frozenset({"os.scandir", "os.listdir"})
_ATTEMPTED: ContextVar[set[str] | None] = ContextVar(
    "pitloom_attempted_listings", default=None
)
_INSTALL_LOCK = threading.Lock()
_hook_installed = False  # pylint: disable=invalid-name


# Not measurable by coverage: CPython runs audit hooks untraced.
def _audit(event: str, args: tuple[object, ...]) -> None:  # pragma: no cover
    """Record the directory a listing call is about to open."""
    if event not in _LISTING_EVENTS:
        return
    attempted = _ATTEMPTED.get()
    if attempted is None:
        return
    # Never raise: an exception here would fail the audited call itself.
    # A file descriptor (os.fwalk) has no path to name: fsdecode() raises.
    try:
        target = args[0] if args else None
        name = "." if target is None else os.fsdecode(target)  # type: ignore[arg-type]
        # abspath() resolves a relative name against the cwd now, while a
        # chdir()ing backend (setuptools, pdm) is still inside project_dir.
        attempted.add(os.path.abspath(name))
    # pylint: disable-next=broad-exception-caught
    except Exception:  # nosec B110
        pass


def _install_hook() -> None:
    global _hook_installed  # pylint: disable=global-statement
    with _INSTALL_LOCK:
        if not _hook_installed:
            sys.addaudithook(_audit)
            _hook_installed = True


def _project_relative(path: str, project_dir: Path) -> str | None:
    """*path* relative to *project_dir* in POSIX form, or ``None`` outside."""
    try:
        return PurePath(path).relative_to(project_dir).as_posix()
    except ValueError:
        return None


def _warn(attempted: set[str], project_dir: Path) -> None:
    for path in sorted(attempted):
        relative = _project_relative(path, project_dir)
        if relative is None:
            continue
        try:
            with os.scandir(path):
                pass
        except OSError as exc:
            if not is_missing_errno(exc):
                log.warning(UNLISTABLE_DIR_WARNING, relative, "for file discovery", exc)


@contextmanager
def warn_unlistable_dirs(project_dir: Path) -> Iterator[None]:
    """Log one ``WARNING:`` per directory under *project_dir* (absolute)
    that the block tried and failed to list; see the module docstring.

    Nothing is logged when the block raises.
    """
    _install_hook()
    attempted: set[str] = set()
    token = _ATTEMPTED.set(attempted)
    try:
        yield
    finally:
        _ATTEMPTED.reset(token)
    _warn(attempted, project_dir)
