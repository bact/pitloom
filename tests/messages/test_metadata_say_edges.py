# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Boundaries of the relay and discovery say helpers found by mutation testing.

See also: ``tests/messages/test_metadata_relays.py``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.core.internal_error import InternalError
from pitloom.messages import CodedValueError
from pitloom.messages.metadata import relay_coded_warning
from pitloom.messages.targets import PROJECT_NOT_FOUND, PROJECT_NOT_FOUND_LINE

_FILE = Path("proj") / "pyproject.toml"
_LOG = logging.getLogger("pitloom.test_relays")


@pytest.mark.parametrize(
    ("exc", "named"),
    [
        (
            CodedValueError(PROJECT_NOT_FOUND, line=PROJECT_NOT_FOUND_LINE, path=_FILE),
            "project-not-found",
        ),
        (RuntimeError("not coded"), "RuntimeError"),
    ],
    ids=["coded-twinless", "uncoded"],
)
def test_the_internal_error_of_a_relay_names_the_error_and_chains_it(
    exc: BaseException, named: str
) -> None:
    """The programming error says which code (or class) has no twin, and
    keeps the error it could not relay as its cause."""
    with pytest.raises(InternalError, match=named) as raised:
        relay_coded_warning(_LOG, exc, quiet=True)
    assert raised.value.__cause__ is exc
