# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A record of the HTTP clients Pitloom fetches through (``urllib3``,
``requests``) is masked as it is made, once :func:`configure_logging` ran,
only where it holds a credential; any other library's record is passed on
as made.

See also: tests/logging/test_credential_sinks_factory.py (``pitloom``
records), src/pitloom/log_masking.py.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator

import pytest

from pitloom import log_masking
from pitloom.log_masking import UNSHOWN_MESSAGE
from pitloom.logging_config import configure_logging

pytestmark = pytest.mark.platform

SECRET = "S3CRET"
TOKEN = "T0KEN"
URL = f"https://u:{SECRET}@h.example/x?token={TOKEN}"


@pytest.fixture(name="root")
def _root() -> Iterator[io.StringIO]:
    """A root handler at ``DEBUG``, the third-party loggers at ``DEBUG`` and
    the ``pitloom`` logger configured (``tests/conftest.py`` resets it and
    the record factory)."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    root.addHandler(handler)
    names = ["urllib3", "requests", "urllib3x"]
    levels = {name: logging.getLogger(name).level for name in names}
    for name in names:
        logging.getLogger(name).setLevel(logging.DEBUG)
    configure_logging()
    try:
        yield stream
    finally:
        root.removeHandler(handler)
        for name, level in levels.items():
            logging.getLogger(name).setLevel(level)


@pytest.mark.parametrize(
    "name", ["urllib3", "urllib3.connectionpool", "requests", "requests.adapters"]
)
def test_a_client_record_with_a_url_is_masked(root: io.StringIO, name: str) -> None:
    logging.getLogger(name).debug("Starting new HTTPS connection (1): %s", URL)
    shown = root.getvalue()
    assert "https://***:***@h.example/x?token=***" in shown
    assert SECRET not in shown and TOKEN not in shown


def test_a_request_target_without_a_scheme_is_masked(root: io.StringIO) -> None:
    """urllib3's own line: the target is a path and its query, no URL."""
    logging.getLogger("urllib3.connectionpool").debug(
        '%s://%s:%s "%s %s %s" %s %s',
        *("https", "h.example", 443, "GET", f"/x?access_token={TOKEN}&a=1"),
        *("HTTP/1.1", 200, None),
    )
    assert '"GET /x?access_token=***&a=1 HTTP/1.1" 200' in root.getvalue()


class _Kept(logging.Handler):
    """Keeps each record it handles."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_a_record_without_a_credential_is_kept_as_made(root: io.StringIO) -> None:
    """No cost to other handlers: template and arguments are the caller's."""
    args = ("h.example", 443)
    handler = _Kept()
    logger = logging.getLogger("urllib3.connectionpool")
    logger.addHandler(handler)
    try:
        logger.debug("Starting new HTTPS connection (1): %s:%s", *args)
    finally:
        logger.removeHandler(handler)
    assert len(handler.records) == 1
    record = handler.records[0]
    assert record.msg == "Starting new HTTPS connection (1): %s:%s"
    assert record.args == args
    assert "h.example:443" in root.getvalue()


@pytest.mark.parametrize("name", ["urllib3x", "thirdparty.urllib3"])
def test_another_logger_is_not_masked(root: io.StringIO, name: str) -> None:
    """A name that only starts like one, or holds one after a dot, is
    another library's (documented scope)."""
    logging.getLogger(name).warning("x %s", URL)
    assert URL in root.getvalue()


def test_a_client_record_is_not_masked_before_configuring() -> None:
    """Documented scope: the factory is installed by ``configure_logging``."""
    record = logging.getLogger("urllib3").makeRecord(
        "urllib3", logging.DEBUG, "f", 1, "x %s", (URL,), None
    )
    assert URL in record.getMessage()


@pytest.mark.usefixtures("root")
def test_a_failing_masker_or_format_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A masker failure shows a fixed text; a format error of the library's
    own is left for the handler to report, as it was."""

    def fail(text: str) -> str:
        raise RuntimeError(text)

    monkeypatch.setattr(log_masking, "mask_free_params", fail)
    log = logging.getLogger("urllib3")
    record = log.makeRecord("urllib3", logging.DEBUG, "f", 1, "x %s", (URL,), None)
    assert record.getMessage() == UNSHOWN_MESSAGE
    bad = log.makeRecord("urllib3", logging.DEBUG, "f", 1, "x %d", ("y",), None)
    assert (bad.msg, bad.args) == ("x %d", ("y",))
