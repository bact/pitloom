# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What ``licenseid`` says while Pitloom asks it, relayed as tagged
``pitloom`` records.

``licenseid`` gives each fallback it takes or guess it makes as a
:class:`licenseid.LicenseIdWarning` through Python's :mod:`warnings`
(``database: build v2 outdated: current v3; run 'licenseid update'``).
Unrelayed, Python prints it in its own format (``<file>:<line>:
LicenseIdWarning: ...`` plus a source line), and a ``-W error`` (or
pytest's ``filterwarnings = ["error"]``) raises it out of the call.
Every ``licenseid`` call Pitloom makes (building the detector, detecting,
resolving) runs inside :func:`relay_licenseid_warnings`, which records
each such warning and says it once per text as ``WARNING: licenseid:
<its text>``; ``variant not stated`` (a guess ``licenseid`` records on the
detection) is ``INFO:``. A warning of any other category recorded in the
block is given again on exit, to the filters in force, so nothing is
swallowed.

The warning filters are process-wide state: the block holds one lock, so
two relays never interleave, and a warning another thread gives meanwhile
is recorded too (a non-``licenseid`` one is given again).

See also: :mod:`pitloom.extract._license` (the callers) and
:mod:`pitloom.core._models_wheel_setuptools_relay` (the same relay for
setuptools).
"""

from __future__ import annotations

import logging
import threading
import warnings
from collections.abc import Iterator
from contextlib import contextmanager

from licenseid import LicenseIdWarning

from pitloom.logging_config import log_once, one_line

log = logging.getLogger(__name__)

#: The sub-prefix of every line said for ``licenseid``.
PREFIX = "licenseid: "

#: Conditions that are a guess recorded on the result, not a fallback: the
#: detection itself says what was read, so the line is ``INFO:``.
_INFO_CONDITIONS = frozenset({"variant not stated"})

#: Held while the warning filters are changed (they are process-wide).
_LOCK = threading.RLock()


def say(text: str, level: int = logging.WARNING) -> None:
    """Log *text*, which ``licenseid`` said, once per process at *level*
    (later repeats at ``DEBUG``), as one escaped line after :data:`PREFIX`."""
    line = PREFIX + one_line(text)
    log_once(log, level, line, "%s", line)


def _relay(caught: list[warnings.WarningMessage]) -> None:
    """Say each ``licenseid`` warning of *caught*; give any other again."""
    for warning in caught:
        message = warning.message
        if isinstance(message, LicenseIdWarning):
            info = message.condition in _INFO_CONDITIONS
            say(str(message), logging.INFO if info else logging.WARNING)
            continue
        warnings.warn_explicit(
            message,
            warning.category,
            warning.filename,
            warning.lineno,
            source=warning.source,
        )


@contextmanager
def relay_licenseid_warnings() -> Iterator[None]:
    """Relay what ``licenseid`` warns in the block (see the module
    docstring), also when the block raises."""
    caught: list[warnings.WarningMessage] = []
    with _LOCK:
        try:
            with warnings.catch_warnings(record=True) as recorded:
                warnings.simplefilter("always", LicenseIdWarning)
                caught = recorded
                yield
        finally:
            _relay(caught)
