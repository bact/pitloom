# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Boundaries of the setuptools stderr relay found by mutation testing.

See also: ``tests/core/models_wheel/test_models_wheel_setuptools_relay.py``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from pitloom.core import _models_wheel_setuptools_relay as relay

pytestmark = pytest.mark.platform

_LOGGER = "pitloom.core._models_wheel_setuptools_relay"
_PREFIX = "setuptools stderr: "


def _relayed(caplog: pytest.LogCaptureFixture) -> list[tuple[int, str]]:
    return [(r.levelno, r.getMessage()) for r in caplog.records if r.name == _LOGGER]


@pytest.mark.parametrize(
    "text",
    ["error without colon", "errors: several", "an error: not first"],
    ids=["no-colon", "plural", "not-first"],
)
def test_only_a_line_that_starts_with_error_colon_is_a_warning(
    text: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        relay.relay_stderr_text(Path("proj"), text)
    assert _relayed(caplog) == [(logging.DEBUG, _PREFIX + text)]


def test_the_real_cap_keeps_64_kib_of_stderr_and_counts_the_rest(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The cap is not patched here: what setuptools writes beyond it is not
    kept, and its size is said."""
    keep = 64 * 1024
    with (
        caplog.at_level(logging.DEBUG, logger=_LOGGER),
        relay.relay_setuptools_output(Path("proj")),
    ):
        sys.stderr.write("x" * (keep + 10))
    messages = _relayed(caplog)
    assert messages[0] == (logging.DEBUG, _PREFIX + "x" * keep)
    assert messages[1][1].endswith("10 more characters not kept")
