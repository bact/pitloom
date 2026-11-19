# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What setuptools says while it reads a target project's config, relayed as
tagged ``pitloom`` log records.

Setuptools speaks two ways during file discovery. Python warnings (a
``SetuptoolsDeprecationWarning`` banner for a ``project.license`` table)
are recorded and logged as one ``DEBUG`` line each. Its manifest step
(``include_package_data``) logs through ``distutils.log``, the root logger,
which with no handler there writes the bare text to ``sys.stderr``
(``warning: no files found matching '*.js'``), and ``distutils.text_file``
writes to ``sys.stderr`` directly. What this thread writes to ``sys.stderr``
is captured, per thread
(:func:`pitloom.extract.stderr_capture.capture_stderr`), and each non-blank
line is logged again after :data:`_PREFIX` (``setuptools stderr: ``):
``WARNING`` when setuptools calls it an ``error:``, ``DEBUG`` otherwise.
Both describe the target project's own config, as a real build would print
it, not a Pitloom deviation; setuptools' own words, so no code: the message
inventory knows this shape as a ``prefixed`` relay
(``scripts/message_inventory/_relay.py``). The project directory is named
by the file discovery lines around it, not here (one project per
discovery). What reaches
``sys.stderr`` from this thread reaches stderr only as a tagged record, and
the text is kept: escaped, one record per line. Not covered: the output of a
subprocess, a write to file descriptor 2 and a handler bound to
``sys.stderr`` that outlives the block.

See also: :mod:`pitloom.core._models_wheel_setuptools` (sole caller).
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pitloom.core.quote_source import quote_source
from pitloom.core.warning_capture import WARNINGS_LOCK, recorded_in_thread
from pitloom.logging_config import one_line

log = logging.getLogger(__name__)

#: Characters of setuptools' stderr kept for relaying; the rest is counted.
STDERR_KEEP = 64 * 1024

#: The line start setuptools/distutils give an error they report and go on.
_ERROR_PREFIX = "error:"

#: The sub-prefix of every line said for setuptools.
_PREFIX = "setuptools stderr: "


def _say_stderr(line: str, level: int) -> None:
    """Log *line*, which setuptools wrote to stderr, at *level*, as one
    escaped line after :data:`_PREFIX`."""
    # The prefix is a constant, the text a %s argument: the shape the
    # message inventory reads as a prefixed relay.
    # pylint: disable-next=logging-not-lazy
    log.log(level, _PREFIX + "%s", one_line(line))


def relay_stderr_text(project_dir: Path, text: str, dropped: int = 0) -> None:
    """Log each non-blank line of *text*, which setuptools wrote to stderr
    while reading *project_dir*, as one tagged record; then, when *dropped*
    characters were not kept, one ``DEBUG`` line saying how many."""
    for line in text.splitlines():
        if not line.strip():
            continue
        is_error = line.lstrip().lower().startswith(_ERROR_PREFIX)
        _say_stderr(line, logging.WARNING if is_error else logging.DEBUG)
    if dropped:
        log.debug(
            "%s: setuptools stderr: %d more characters not kept",
            quote_source(project_dir),
            dropped,
        )


@contextmanager
def _relayed_stderr(project_dir: Path) -> Iterator[None]:
    """Capture this thread's ``sys.stderr`` writes in the block, then relay
    them once the capture is left (a ``pitloom`` record logged while it is
    on could itself land in the sink)."""
    # pylint: disable-next=import-outside-toplevel
    from pitloom.extract.stderr_capture import BoundedStderr, capture_stderr

    sinks: list[BoundedStderr] = []
    try:
        with capture_stderr(STDERR_KEEP) as sink:
            sinks.append(sink)
            yield
    finally:
        for sink in sinks:
            relay_stderr_text(project_dir, sink.text(), sink.dropped)


def _any_warning(message: Warning | str) -> bool:
    del message
    return True


@contextmanager
def relay_setuptools_output(project_dir: Path) -> Iterator[None]:
    """Relay what setuptools says in the block, in this thread, as tagged
    ``pitloom`` records (see the module docstring), also when the block
    raises.

    The warning filters are changed only inside
    :func:`warnings.catch_warnings`, restored on exit, under
    :data:`pitloom.core.warning_capture.WARNINGS_LOCK`, so no other block of
    Pitloom that changes them overlaps this one. They are process-wide
    state: meanwhile a warning of another thread is given under ``always``
    too, and goes on to Python, not into this record
    (:func:`pitloom.core.warning_capture.recorded_in_thread`).
    :func:`pitloom.core._models_wheel_setuptools.discover` runs under the
    discovery lock's exclusive mode, which keeps every other discovery out.
    """
    caught: list[warnings.WarningMessage] = []
    try:
        with WARNINGS_LOCK, warnings.catch_warnings():
            warnings.simplefilter("always")
            with (
                recorded_in_thread(_any_warning) as caught,
                _relayed_stderr(project_dir),
            ):
                yield
    finally:
        for warning in caught:
            log.debug(
                "%s: setuptools %s: %s",
                quote_source(project_dir),
                warning.category.__name__,
                one_line(warning.message),
            )
