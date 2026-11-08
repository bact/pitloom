# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What LicenseID says while Pitloom asks it, relayed as tagged
``pitloom`` records.

LicenseID gives each fallback it takes or guess it makes as a
:class:`licenseid.LicenseIdWarning` through Python's :mod:`warnings`
(``database: build v3 outdated: current v4; run 'licenseid update'``).
Unrelayed, Python prints it in its own format (``<file>:<line>:
LicenseIdWarning: ...`` plus a source line), and a ``-W error`` (or
pytest's ``filterwarnings = ["error"]``) raises it out of the call.
Every LicenseID call Pitloom makes (building the detector, detecting,
resolving) runs inside :func:`relay_licenseid_warnings`, which records
each such warning and says it once per text as ``WARNING: licenseid:
<its text>``; ``variant not stated`` (a guess LicenseID records on the
detection) is ``INFO:``, and ``too few words for text`` (no licence found
in a short text) is ``DEBUG`` (:data:`_LEVELS`).

LicenseID attributes its warning to the code that called it, a
``pitloom`` module. One filter, ``always`` for a
:class:`licenseid.LicenseIdWarning` of a ``pitloom`` module
(:data:`_MODULE`), keeps it from being raised or ignored; it is put first
in the filters when it is not already there and then left in place, so a
lookup does not change the filters (a change resets Python's "once per
location" record of every warning in the process). The filters for a
LicenseID warning given to other code, and for any other warning, are
the host's. The block records only what this thread is shown
(:func:`pitloom.core.warning_capture.recorded_in_thread`): any other
warning goes on to Python as it would without the relay, when it is given.

The block holds :data:`pitloom.core.warning_capture.WARNINGS_LOCK`, which
every block of Pitloom that changes the warning state holds, so none of
them overlaps it. A block of other code that replaces
``warnings.showwarning`` in another thread while a lookup runs (an
overlapping :class:`warnings.catch_warnings` with ``record=True``) takes
the LicenseID warnings given meanwhile, which are then not said; after
both, no warning is taken or dropped.

See also: :mod:`pitloom.extract._license_resolve` and
:mod:`pitloom.extract._license_text_match` (the callers) and
:mod:`pitloom.core._models_wheel_setuptools_relay` (the same relay for
setuptools).
"""

from __future__ import annotations

import logging
import re
import warnings
from collections.abc import Iterator
from contextlib import contextmanager

from licenseid import LicenseIdWarning

from pitloom.core.warning_capture import WARNINGS_LOCK, recorded_in_thread
from pitloom.logging_config import log_once, one_line

log = logging.getLogger(__name__)

#: The sub-prefix of every line said for LicenseID.
PREFIX = "licenseid: "

#: The level of a condition said below ``WARNING``; any other is a fallback
#: or failure, said at ``WARNING``. ``variant not stated`` is a guess
#: recorded on the result (the detection says what was read): ``INFO:``.
#: ``too few words for text`` only says a text is too short to match, so
#: no licence was found in it: absent data, quiet at ``DEBUG``.
_LEVELS: dict[str, int] = {
    "variant not stated": logging.INFO,
    "too few words for text": logging.DEBUG,
}

#: The modules whose LicenseID warnings the relay's filter takes: a
#: warning is attributed to the module that called LicenseID.
_MODULE = r"pitloom(\.|$)"

#: The relay's filter as :func:`warnings.filterwarnings` stores it.
_FILTER = ("always", None, LicenseIdWarning, re.compile(_MODULE), 0)


def say(text: str, level: int = logging.WARNING) -> None:
    """Log *text*, which LicenseID said, once per process at *level*
    (later repeats at ``DEBUG``), as one escaped line after :data:`PREFIX`."""
    line = PREFIX + one_line(text)
    log_once(log, level, line, "%s", line)


def _is_licenseid_warning(message: Warning | str) -> bool:
    return isinstance(message, LicenseIdWarning)


def _relay(caught: list[warnings.WarningMessage]) -> None:
    """Say each LicenseID warning of *caught*."""
    for warning in caught:
        message = warning.message
        if isinstance(message, LicenseIdWarning):
            say(str(message), _LEVELS.get(message.condition, logging.WARNING))


def _keep_filter_first() -> None:
    """Put :data:`_FILTER` first, unless it already is: adding a filter is
    a change, which Python marks by resetting every "once per location"
    record."""
    if warnings.filters[:1] != [_FILTER]:
        warnings.filterwarnings("always", category=LicenseIdWarning, module=_MODULE)


@contextmanager
def relay_licenseid_warnings() -> Iterator[None]:
    """Relay what LicenseID warns in the block (see the module
    docstring), also when the block raises."""
    caught: list[warnings.WarningMessage] = []
    with WARNINGS_LOCK:
        try:
            _keep_filter_first()
            with recorded_in_thread(_is_licenseid_warning) as recorded:
                caught = recorded
                yield
        finally:
            _relay(caught)
