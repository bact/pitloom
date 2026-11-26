# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""How :func:`pitloom.extract._extract_utils.fetch_json` words a failed fetch:
which failures are a timeout, which the reason a line shows and the seconds
it names.

See also: tests/extract/test_extract_utils.py.
"""

from __future__ import annotations

import urllib.request
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import pytest

from pitloom.extract._extract_utils import fetch_json
from pitloom.messages import Message as Entry
from pitloom.messages.network import DOWNLOAD_FAILED, DOWNLOAD_TIMEOUT
from tests._message_drift import raised_as

_USE = "for the Croissant document"
_URL = "https://example.com/c.json"


def _fetch_failing_with(exc: BaseException, timeout: float = 30.0) -> ValueError:
    with patch.object(urllib.request, "urlopen", side_effect=exc):
        with pytest.raises(ValueError) as raised:
            fetch_json(_URL, timeout=timeout, use=_USE)
    return raised.value


@pytest.mark.parametrize(
    ("make", "said"),
    [
        (
            lambda: URLError(ConnectionRefusedError(61, "Connection refused")),
            "Connection refused",
        ),
        (
            lambda: ConnectionResetError(54, "Connection reset by peer"),
            "Connection reset by peer",
        ),
    ],
    ids=["refused-in-url-error", "reset"],
)
def test_a_refused_or_reset_connection_is_a_failure_not_a_timeout(
    make: Callable[[], BaseException], said: str
) -> None:
    """Only a socket timeout is ``download-timeout``: a refused or reset
    connection is an ``OSError`` too, but ``download-network-failed``. The
    line shows the underlying reason, not the ``URLError`` wrapper."""
    error = _fetch_failing_with(make())
    assert raised_as(error, DOWNLOAD_FAILED)
    assert not raised_as(error, DOWNLOAD_TIMEOUT)
    assert str(error) == f"URL={_URL}: {said}; not read"
    assert "<urlopen error" not in str(error)


@pytest.mark.parametrize(
    ("timeout", "duration"),
    [(0.5, "1 second"), (2.1, "3 seconds"), (3.0, "3 seconds")],
    ids=["below-one-is-one", "rounded-up", "whole"],
)
def test_a_timeout_names_whole_seconds_rounded_up_never_below_one(
    timeout: float, duration: str
) -> None:
    entry: Entry = DOWNLOAD_TIMEOUT
    error = _fetch_failing_with(TimeoutError("timed out"), timeout)
    assert raised_as(error, entry)
    assert str(error) == (f"URL={_URL}: no complete answer within {duration}; not read")


def test_a_missing_file_error_hides_the_os_error_behind_it(tmp_path: Path) -> None:
    """The ``FileNotFoundError`` is not the cause shown: the line says it."""
    with pytest.raises(ValueError) as raised:
        fetch_json(tmp_path / "absent.json", use=_USE)
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True
