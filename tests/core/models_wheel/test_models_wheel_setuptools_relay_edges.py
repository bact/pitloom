# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Boundaries of the setuptools stderr relay found by mutation testing, and
its text masked before it is split.

See also: ``tests/core/models_wheel/test_models_wheel_setuptools_relay.py``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from pitloom.core import _models_wheel_setuptools_relay as relay
from pitloom.logging_config import configure_logging

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


@pytest.mark.parametrize("brk", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_relays_mask_before_they_split(
    brk: str,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Split first, each line would hold a harmless-looking piece of the
    password: ``error: fetch https://u:S3cr`` and ``3tPw99x@h/x``."""
    configure_logging(debug=True)
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        relay.relay_stderr_text(
            Path("proj"), f"error: fetch https://u:S3cr{brk}3tPw99x@h/x{brk}"
        )
    err = capsys.readouterr().err
    texts = [message for _, message in _relayed(caplog)] + [err]
    assert not any("S3cr" in t or "3tPw99x" in t for t in texts)
    assert _relayed(caplog) == [
        (logging.WARNING, _PREFIX + "error: fetch https://***:***@h/x")
    ]
