# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Reader/writer concurrency lock for backend file discovery.

Split out of :mod:`pitloom.core._models_wheel_dispatch` once that file
(and its sibling :mod:`pitloom.core._models_wheel`) crossed the
~400-500 line soft limit -- a self-contained concurrency primitive with
no dependency on the dispatch logic that uses it.

See also: :mod:`pitloom.core._models_wheel_dispatch`, the sole caller.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from pitloom.core.internal_error import InternalError


class _DiscoveryLock:
    """Multiple concurrent readers, or one exclusive writer -- never both.
    Writer-priority: once a writer is waiting, no *new* reader is admitted
    ahead of it, so a continuous stream of freshly-arriving readers can
    never starve a writer out indefinitely -- it only ever waits for
    readers already in flight at the moment it arrived.

    A "writer" (a backend registered with ``needs_write_lock=True`` in
    :class:`pitloom.core._models_wheel_dispatch._RegisteredBackend` --
    currently setuptools and PDM-backend) process-wide ``os.chdir()``s
    for the duration of its call and must run with no other discoverer
    -- reader or writer -- active. A "reader" (every other backend, e.g.
    Hatchling's, Poetry's, or Flit's ``discover()``) never touches cwd
    itself (``get_wheel_files`` always resolves *project_dir* to an
    absolute path first), so readers never need to block each other --
    only a concurrent writer. Held here, at the sole dispatch point
    every backend's ``discover()`` funnels through, so a future backend
    module needs no lock of its own to get the same guarantee; a future
    *writer*-style backend should register with ``needs_write_lock=True``
    the same way setuptools/PDM-backend do.

    Deliberate exception: the generic build-and-read mechanism
    (:mod:`pitloom.core._models_wheel_build_and_read`, invoked via
    ``--allow-build``) does NOT go through this lock at all, in either
    mode -- it provably touches no process-wide mutable state (the real
    build runs in a subprocess with its own explicit ``cwd=``, never
    Pitloom's own), so it needs neither a reader's nor a writer's
    guarantee. It is also categorically slower (network, venv creation,
    a real build -- seconds to tens of seconds) than every in-process
    backend here; holding even a read lock around it would block a
    concurrent writer for the entire build duration, a large, surprising
    latency coupling with no actual state to protect. See
    ``_try_build_and_read`` in :mod:`pitloom.core._models_wheel_dispatch`,
    which calls it unguarded.

    Both ``read()`` and ``write()`` guard against re-entrant acquisition
    by the thread already holding the write lock: a writer backend's own
    ``discover()`` (setuptools imports the target project's ``setup.py``,
    PDM-backend runs the project's own build hooks -- both arbitrary
    third-party code) that calls back into file discovery -- through
    *either* a reader backend (Hatchling, Poetry, Flit) or another
    writer -- while already holding the write lock would otherwise
    deadlock against itself, since only that same thread could ever
    release it. Both methods raise ``InternalError`` immediately instead.
    (The build-and-read mechanism above is a separate matter: it never
    holds this lock in the first place, so it cannot trigger this case.)
    """

    def __init__(self) -> None:
        self._cond = threading.Condition(threading.Lock())
        self._readers = 0
        self._writer_active = False
        self._writers_waiting = 0
        self._writer_thread: int | None = None

    def _raise_if_reentrant_writer(self, ident: int) -> None:
        if self._writer_active and self._writer_thread == ident:
            raise InternalError(
                "_DiscoveryLock.read()/write() called re-entrantly by "
                "the thread that already holds the write lock -- this "
                "would deadlock. A writer backend's discover() (or "
                "third-party code it runs) must never call back into "
                "file discovery while the write lock is already held."
            )

    @contextmanager
    def read(self) -> Iterator[None]:
        with self._cond:
            self._raise_if_reentrant_writer(threading.get_ident())
            while self._writer_active or self._writers_waiting > 0:
                self._cond.wait()
            self._readers += 1
        try:
            yield
        finally:
            with self._cond:
                self._readers -= 1
                if self._readers == 0:
                    self._cond.notify_all()

    @contextmanager
    def write(self) -> Iterator[None]:
        ident = threading.get_ident()
        with self._cond:
            self._raise_if_reentrant_writer(ident)
            self._writers_waiting += 1
            try:
                while self._writer_active or self._readers > 0:
                    self._cond.wait()
            finally:
                self._writers_waiting -= 1
            self._writer_active = True
            self._writer_thread = ident
        try:
            yield
        finally:
            with self._cond:
                self._writer_active = False
                self._writer_thread = None
                self._cond.notify_all()


_DISCOVERY_LOCK = _DiscoveryLock()
