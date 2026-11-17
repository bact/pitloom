# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The coded lines a test captured, for an assertion on a line's ``[code]``
and a short stable part of its text, never the whole line.
"""

from __future__ import annotations

import pytest

from pitloom.logging_config import CODE_ATTR


def coded(caplog: pytest.LogCaptureFixture) -> list[tuple[str | None, str]]:
    """``(code, message)`` of each record *caplog* holds, in order; the code
    is ``None`` for a line the catalogue does not say."""
    return [
        (getattr(record, CODE_ATTR, None), record.getMessage())
        for record in caplog.records
    ]


def has_parts(message: str, *parts: str) -> bool:
    """Whether *message* holds every one of *parts*."""
    return all(part in message for part in parts)
