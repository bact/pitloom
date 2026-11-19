# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The file discovery say helper refuses a line of another entry.

See also: ``tests/messages/test_metadata_discovery.py`` (the lines said).
"""

from __future__ import annotations

import logging

import pytest

from pitloom.core.internal_error import InternalError
from pitloom.messages._metadata_say import warn_discovery
from pitloom.messages.metadata import METADATA_INVALID


def test_a_line_that_is_no_file_discovery_line_is_an_internal_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A programming error, never an uncoded line: nothing is said."""
    line = METADATA_INVALID.lines[0]
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(InternalError, match="no file discovery line"):
            warn_discovery(logging.getLogger("pitloom.test_say"), line)
    assert not caplog.records
