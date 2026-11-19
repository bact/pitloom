# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``dependency-name-ambiguous``: a direct reference is said as an ``INFO:``
line naming the package only, once per package (by its PEP 503 name) and
memo, never through ``log_once``.

See also: tests/messages/test_dependency_skips.py.
"""

from __future__ import annotations

import logging

import pytest

from pitloom.logging_config import CODE_ATTR
from pitloom.messages import trusted_message
from pitloom.messages.dependencies import (
    DEPENDENCY_NAME_AMBIGUOUS,
    say_direct_reference,
)

_LOG = logging.getLogger("pitloom.direct_reference_messages")


def test_a_direct_reference_is_said_once_per_package(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    said: set[str] = set()
    for name in ("My_Pkg", "my-pkg", "my.pkg"):
        say_direct_reference(_LOG, name, said=said)
    say_direct_reference(_LOG, "other", said=said)
    lines = [
        f"{r.levelname}: {r.getMessage()} [{getattr(r, CODE_ATTR)}]"
        for r in caplog.records
    ]
    assert lines == [
        "INFO: PACKAGE=My_Pkg: a direct reference; not looked up on PyPI "
        "[dependency-name-ambiguous]",
        "INFO: PACKAGE=other: a direct reference; not looked up on PyPI "
        "[dependency-name-ambiguous]",
    ]
    assert all(trusted_message(line) is DEPENDENCY_NAME_AMBIGUOUS for line in lines)


def test_a_new_document_says_it_again(caplog: pytest.LogCaptureFixture) -> None:
    """Per run, never per process: a second library call still says it."""
    caplog.set_level(logging.INFO)
    for _ in range(2):
        say_direct_reference(_LOG, "a", said=set())
    assert [r.levelno for r in caplog.records] == [logging.INFO, logging.INFO]


def test_a_control_character_in_the_name_is_escaped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    say_direct_reference(_LOG, "a\nINFO: forged", said=set())
    (record,) = caplog.records
    assert "\n" not in record.getMessage()
