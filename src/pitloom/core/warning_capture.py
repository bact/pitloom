# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one lock Pitloom holds while it changes Python's warning state, and
a per-thread recorder of warnings.

The warning filters and :func:`warnings.showwarning` are process-wide (on
Python 3.14 with context-aware warnings the filters are per context, but
``showwarning`` is not). Two blocks of two threads that each change and
restore them, in overlapping order, can leave the state of the one that
entered second in force for good: a recording ``showwarning`` then takes
every later warning of the process into a list nobody reads. Every block of
Pitloom that changes that state (the ``licenseid`` relay, the setuptools
relay, the usage scan's parse) holds :data:`WARNINGS_LOCK` for the whole
block, so no two of them overlap. Code outside Pitloom (the host, another
library) does not take it.

:func:`recorded_in_thread` records only what is shown in the thread that
entered it and hands everything else to the ``showwarning`` it replaced, so
a warning of another thread is never taken. Left in place by an
overlapping block of other code, it records nothing more and forwards
every warning.

See also: :mod:`pitloom.extract._licenseid_relay` and
:mod:`pitloom.core._models_wheel_setuptools_relay` (the relays),
:mod:`pitloom.extract.stderr_capture` (the same per-thread shape, for
``sys.stderr``).
"""

from __future__ import annotations

import threading
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Protocol, TextIO

__all__ = ["WARNINGS_LOCK", "recorded_in_thread"]


# pylint: disable-next=too-few-public-methods
class _ShowWarning(Protocol):
    """The signature of :func:`warnings.showwarning`."""

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def __call__(
        self,
        message: Warning | str,
        category: type[Warning],
        filename: str,
        lineno: int,
        file: TextIO | None = None,
        line: str | None = None,
    ) -> None: ...


#: Held for a whole block of Pitloom's that changes the warning filters or
#: ``warnings.showwarning``. Reentrant: a relay may run inside another of
#: the same thread. Never held while waiting for another thread.
WARNINGS_LOCK = threading.RLock()


# pylint: disable-next=too-few-public-methods
class _Recorder:
    """Stands in for ``warnings.showwarning`` while a block records."""

    def __init__(
        self, previous: _ShowWarning, accept: Callable[[Warning | str], bool]
    ) -> None:
        self.previous: _ShowWarning = previous
        self.caught: list[warnings.WarningMessage] = []
        self.active: bool = True
        self._accept = accept
        self._owner = threading.get_ident()

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def __call__(
        self,
        message: Warning | str,
        category: type[Warning],
        filename: str,
        lineno: int,
        file: TextIO | None = None,
        line: str | None = None,
    ) -> None:
        if (
            self.active
            and threading.get_ident() == self._owner
            and self._accept(message)
        ):
            self.caught.append(
                warnings.WarningMessage(message, category, filename, lineno, file, line)
            )
            return
        self.previous(message, category, filename, lineno, file, line)


@contextmanager
def recorded_in_thread(
    accept: Callable[[Warning | str], bool],
) -> Iterator[list[warnings.WarningMessage]]:
    """Record each warning shown in this thread in the block that *accept*
    takes; give every other one to the ``showwarning`` in force on entry.
    A warning the filters raise or ignore is never shown, so never recorded.

    The caller holds :data:`WARNINGS_LOCK`. On exit the replaced
    ``showwarning`` is put back unless something else replaced it meanwhile
    (theirs to restore)."""
    recorder = _Recorder(warnings.showwarning, accept)
    warnings.showwarning = recorder
    try:
        yield recorder.caught
    finally:
        recorder.active = False
        if warnings.showwarning is recorder:
            warnings.showwarning = recorder.previous
