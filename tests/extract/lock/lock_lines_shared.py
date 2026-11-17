# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Assertions on the coded lines a lock reader said: a ``[code]`` and a few
stable parts of the text (``FILE=uv.lock``, ``PACKAGE=name``), never a whole
line.

See also: tests/_code_records.py (the capture these build on).
"""

from __future__ import annotations

import pytest

from tests._code_records import coded, has_parts


def matching(caplog: pytest.LogCaptureFixture, code: str, *parts: str) -> list[str]:
    """The captured lines that carry *code* and hold every one of *parts*."""
    return [
        message
        for line_code, message in coded(caplog)
        if line_code == code and has_parts(message, *parts)
    ]


def said(caplog: pytest.LogCaptureFixture, code: str, *parts: str) -> None:
    """Assert that some captured line carries *code* and holds *parts*."""
    assert matching(caplog, code, *parts), coded(caplog)


def said_once(caplog: pytest.LogCaptureFixture, code: str, *parts: str) -> None:
    """Assert that exactly one captured line carries *code* and holds
    *parts*."""
    assert len(matching(caplog, code, *parts)) == 1, coded(caplog)
