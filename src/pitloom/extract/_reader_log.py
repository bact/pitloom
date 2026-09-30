# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Capture of the log records an AI model reader emits.

A reader names a file by the path it was given, and quotes member names of
the archive it reads; the scanner hands it a temporary copy, and the
archive is untrusted. The scanner captures the records while a reader runs
and logs them again under the stable ``FORMAT=``/``FILE=`` prefix, with the
text escaped and the temporary path removed: one route for every reader,
present and future.

See also: :mod:`pitloom.extract.scanner`.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator

#: The logger every reader's own logger is a child of.
_READERS_LOGGER = "pitloom.extract.ai_model"


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextlib.contextmanager
def capture_reader_logs() -> Iterator[list[logging.LogRecord]]:
    """Collect, instead of passing on, what the readers log in the block.

    The list is complete once the block is left. Records are not logged
    by this function; the caller logs the ones it wants.
    """
    logger = logging.getLogger(_READERS_LOGGER)
    handler = _ListHandler()
    propagate = logger.propagate
    logger.addHandler(handler)
    logger.propagate = False
    try:
        yield handler.records
    finally:
        logger.removeHandler(handler)
        logger.propagate = propagate
