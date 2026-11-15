# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A refused URL's secret is not in the text of the failure: an
:class:`http.client.InvalidURL` quotes the URL's path without its scheme
(``'/x?token=...'``), where no URL masking finds a parameter.

See also: tests/logging/test_credential_sinks_cut.py,
tests/core/url_masking/test_url_masking_credentials.py.
"""

from __future__ import annotations

import http.client
import logging
import urllib.request
from collections.abc import Callable

import pytest

from pitloom.extract._extract_utils import fetch_json
from pitloom.extract.remote._http_errors import failed_error, warn_instead
from pitloom.extract.remote._http_watch import Watch
from pitloom.logging_config import failure_reason
from pitloom.messages._field_writers import failure_text

SECRET = "PLANTSECRET"
#: A space makes ``http.client`` refuse the path before any connection.
URL = f"http://127.0.0.1:9/x?token={SECRET} x"


def _refused() -> http.client.InvalidURL:
    """The exception the standard library raises for :data:`URL`."""
    with pytest.raises(http.client.InvalidURL) as caught:
        with urllib.request.urlopen(URL, timeout=1):  # nosec B310
            pass
    assert SECRET in str(caught.value)  # the text quotes the secret
    return caught.value


@pytest.mark.parametrize("write", [failure_reason, failure_text])
def test_the_failure_text_quotes_no_secret(
    write: Callable[[BaseException], str],
) -> None:
    """Only the text before the quoted path is written."""
    assert write(_refused()) == "URL can't contain control characters."


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("nonnumeric port: 'x?token=S'", "nonnumeric port"),
        ("'/x?token=S'", "InvalidURL"),
        ('bad "/x?token=S"', "bad"),
    ],
    ids=["port", "only-quoted", "double-quote"],
)
def test_an_invalid_url_text_is_cut_at_its_quote(text: str, shown: str) -> None:
    """The cut falls at a quote opening a value, not at an apostrophe."""
    assert failure_reason(http.client.InvalidURL(text)) == shown


def test_fetch_json_raises_without_the_secret() -> None:
    """The ``ValueError`` a library caller gets names no secret."""
    with pytest.raises(ValueError, match="control characters") as caught:
        fetch_json(URL, use="test")
    assert SECRET not in str(caught.value)


def test_a_failed_download_and_its_warning_quote_no_secret(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The client's error, and the ``WARNING:`` of a caller going on
    without the file (``warn_instead``), name neither the secret."""
    error = failed_error(URL, _refused(), Watch(100.0), "pypi")
    assert SECRET not in str(error)
    assert "control characters" in str(error)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        warn_instead(logging.getLogger("pitloom.test"), error, "not read")
    assert caplog.records and "control characters" in caplog.text
    assert SECRET not in caplog.text
