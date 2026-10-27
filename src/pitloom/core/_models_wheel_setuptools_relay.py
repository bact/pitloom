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
line is logged again: ``WARNING`` when setuptools calls it an ``error:``,
``DEBUG`` otherwise. Both describe the target project's own config, as a
real build would print it, not a Pitloom deviation. What reaches
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
from pitloom.logging_config import one_line

log = logging.getLogger(__name__)

#: Characters of setuptools' stderr kept for relaying; the rest is counted.
STDERR_KEEP = 64 * 1024

#: The line start setuptools/distutils give an error they report and go on.
_ERROR_PREFIX = "error:"


def relay_stderr_text(project_dir: Path, text: str, dropped: int = 0) -> None:
    """Log each non-blank line of *text*, which setuptools wrote to stderr
    while reading *project_dir*, as one tagged record; then, when *dropped*
    characters were not kept, one ``DEBUG`` line saying how many."""
    source = quote_source(project_dir)
    for line in text.splitlines():
        if not line.strip():
            continue
        is_error = line.lstrip().lower().startswith(_ERROR_PREFIX)
        log.log(
            logging.WARNING if is_error else logging.DEBUG,
            "%s: setuptools stderr: %s",
            source,
            one_line(line),
        )
    if dropped:
        log.debug("%s: setuptools stderr: %d more characters not kept", source, dropped)


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


@contextmanager
def relay_setuptools_output(project_dir: Path) -> Iterator[None]:
    """Relay what setuptools says in the block, in this thread, as tagged
    ``pitloom`` records (see the module docstring), also when the block
    raises.

    The warning filters are changed only inside
    :func:`warnings.catch_warnings`, restored on exit; that is process-wide
    state, so a warning another thread raises meanwhile is recorded too --
    :func:`pitloom.core._models_wheel_setuptools.discover` runs under the
    discovery lock's exclusive mode, which keeps every other discovery out.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            with _relayed_stderr(project_dir):
                yield
        finally:
            for warning in caught:
                log.debug(
                    "setuptools %s: %s",
                    warning.category.__name__,
                    one_line(warning.message),
                )
