# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``tests/_network_retry.py``: only a transient server answer is
retried, with injected waits so no test sleeps.

See also: tests/_network_retry.py, tests/test_network_helpers.py.
"""

from __future__ import annotations

import logging
import socket
import ssl
import tempfile
import urllib.error
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from email.message import Message
from pathlib import Path

import pytest

from pitloom.extract.remote.errors import RemoteSourceError
from tests._network_retry import (
    RETRY_DELAYS,
    retry_on_transient_server_error,
    transient_server_cause_in_text,
    transient_server_cause_of,
)

# What the release gate saw from git.savannah.gnu.org.
_SAVANNAH = (
    "fatal: unable to access 'https://git.savannah.gnu.org/git/hello.git/': "
    "RPC failed; HTTP 500 curl 22 The requested URL returned error: 500\n"
    "fatal: expected flush after ref listing"
)


def _http(code: int) -> urllib.error.HTTPError:
    """A closed HTTPError: an unclosed one warns at GC on Python 3.14."""
    exc = urllib.error.HTTPError("https://x.test/", code, "msg", Message(), None)
    exc.close()
    return exc


def _git(message: str) -> RemoteSourceError:
    return RemoteSourceError("git.clone-failed", message)


def _wrapped(inner: BaseException) -> ValueError:
    """A ``ValueError`` raised ``from`` *inner*, as ``fetch_json`` does."""
    try:
        raise ValueError("Cannot read source") from inner
    except ValueError as exc:
        return exc


@pytest.mark.parametrize(
    ("exc", "transient"),
    [
        pytest.param(_http(500), True, id="http-500"),
        pytest.param(_http(503), True, id="http-503"),
        pytest.param(_http(599), True, id="http-599"),
        pytest.param(_http(429), True, id="http-429"),
        pytest.param(_http(408), True, id="http-408"),
        pytest.param(_http(404), False, id="http-404"),
        pytest.param(_http(403), False, id="http-403"),
        pytest.param(_http(499), False, id="http-499"),
        pytest.param(_http(301), False, id="http-301"),
        pytest.param(_git(_SAVANNAH), True, id="git-savannah"),
        pytest.param(_git("RPC failed; HTTP 502 curl 22"), True, id="git-rpc-502"),
        pytest.param(_git("... returned error: 503"), True, id="git-returned-503"),
        pytest.param(_git("... returned error: 429"), True, id="git-returned-429"),
        pytest.param(_git("fatal: expected flush after ref listing"), True, id="flush"),
        pytest.param(_git("... returned error: 404"), False, id="git-404"),
        pytest.param(_git("... returned error: 403"), False, id="git-403"),
        pytest.param(_git("RPC failed; HTTP 4000 x"), False, id="git-http-4000"),
        pytest.param(_git("HTTP 5000"), False, id="git-http-5000"),
        pytest.param(_git("Could not resolve host: h"), False, id="git-dns"),
        pytest.param(_git("Failed to connect to h port 443"), False, id="git-refused"),
        pytest.param(_git("gnutls_handshake() failed"), False, id="git-tls"),
        pytest.param(RemoteSourceError("git.timeout", "exceeded 600s"), False, id="to"),
        pytest.param(urllib.error.URLError("refused"), False, id="url-error"),
        pytest.param(ConnectionRefusedError("refused"), False, id="refused"),
        pytest.param(socket.gaierror(-2, "Name or service not known"), False, id="dns"),
        pytest.param(ssl.SSLError("CERTIFICATE_VERIFY_FAILED"), False, id="tls"),
        pytest.param(TimeoutError("timed out"), False, id="timeout"),
        pytest.param(ValueError("HTTP 500 in a plain ValueError"), False, id="plain"),
        pytest.param(_wrapped(_http(502)), True, id="chain-502"),
        pytest.param(_wrapped(_http(404)), False, id="chain-404"),
    ],
)
def test_only_a_transient_server_answer_is_transient(
    exc: BaseException, transient: bool
) -> None:
    assert (transient_server_cause_of(exc) is not None) is transient


@pytest.mark.parametrize(
    ("text", "found"),
    [
        pytest.param(_SAVANNAH, "HTTP 500", id="savannah"),
        pytest.param(
            "The requested URL returned error: 504", "returned error: 504", id="504"
        ),
        pytest.param("HTTP Error 502: Bad Gateway", "HTTP Error 502", id="urllib"),
        pytest.param("returned error: 404", None, id="404"),
        pytest.param("HTTP 40x", None, id="no-digits"),
        pytest.param("", None, id="empty"),
    ],
)
def test_text_classifier(text: str, found: str | None) -> None:
    assert transient_server_cause_in_text(text) == found


# A call counter and a failure script: nothing more to expose.
# pylint: disable-next=too-few-public-methods
class _Flaky:
    """Raise each of *failures* in turn, then return ``"ok"``."""

    def __init__(self, *failures: BaseException) -> None:
        self.failures = list(failures)
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return "ok"


def test_default_waits_are_five_then_twenty_seconds() -> None:
    assert RETRY_DELAYS == (5.0, 20.0)


def test_success_needs_no_retry_and_no_wait() -> None:
    func = _Flaky()
    waits: list[float] = []
    assert retry_on_transient_server_error(func, sleep=waits.append) == "ok"
    assert (func.calls, waits) == (1, [])


def test_one_retry_after_a_transient_answer(caplog: pytest.LogCaptureFixture) -> None:
    func = _Flaky(_git(_SAVANNAH))
    waits: list[float] = []
    with caplog.at_level(logging.INFO, logger="tests._network_retry"):
        assert retry_on_transient_server_error(func, sleep=waits.append) == "ok"
    assert (func.calls, waits) == (2, [5.0])
    assert [r.levelno for r in caplog.records] == [logging.INFO]
    assert "attempt 1 of 3" in caplog.text and "retrying in 5 s" in caplog.text


def test_two_retries_wait_five_then_twenty_seconds() -> None:
    func = _Flaky(_http(500), _http(502))
    waits: list[float] = []
    assert retry_on_transient_server_error(func, sleep=waits.append) == "ok"
    assert (func.calls, waits) == (3, [5.0, 20.0])


def test_the_last_error_is_raised_after_three_attempts() -> None:
    errors = [_http(500), _http(502), _http(503)]
    func = _Flaky(*errors)
    waits: list[float] = []
    with pytest.raises(urllib.error.HTTPError) as caught:
        retry_on_transient_server_error(func, sleep=waits.append)
    assert caught.value is errors[-1]
    assert (func.calls, waits) == (3, [5.0, 20.0])


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(_http(404), id="404"),
        pytest.param(_http(403), id="403"),
        pytest.param(_git("Could not resolve host: h"), id="dns"),
        pytest.param(ConnectionRefusedError("refused"), id="refused"),
        pytest.param(ssl.SSLError("handshake"), id="tls"),
        pytest.param(AssertionError("a real failure"), id="assertion"),
    ],
)
def test_anything_else_is_raised_at_once(exc: BaseException) -> None:
    func = _Flaky(exc, _http(500))
    waits: list[float] = []
    with pytest.raises(type(exc)) as caught:
        retry_on_transient_server_error(func, sleep=waits.append)
    assert caught.value is exc
    assert (func.calls, waits) == (1, [])


def test_a_non_transient_error_after_a_transient_one_stops_the_retries() -> None:
    func = _Flaky(_http(503), _http(404), _http(503))
    waits: list[float] = []
    with pytest.raises(urllib.error.HTTPError, match="404"):
        retry_on_transient_server_error(func, sleep=waits.append)
    assert (func.calls, waits) == (2, [5.0])


def test_custom_delays_set_the_attempt_count() -> None:
    func = _Flaky(*[_http(500)] * 5)
    waits: list[float] = []
    with pytest.raises(urllib.error.HTTPError):
        retry_on_transient_server_error(func, delays=(1.0,), sleep=waits.append)
    assert (func.calls, waits) == (2, [1.0])


def test_a_failed_attempt_entering_a_context_leaves_nothing_open(
    tmp_path: Path,
) -> None:
    """The live Git test enters ``fetch_git_project`` (a generator context
    over a ``TemporaryDirectory``) through an ``ExitStack`` inside the retry:
    a failed attempt has removed its directory, the successful one is kept
    until the stack closes."""
    made: list[Path] = []
    failures = [_git(_SAVANNAH)]

    @contextmanager
    def fetch() -> Iterator[Path]:
        with tempfile.TemporaryDirectory(dir=tmp_path) as work_dir:
            made.append(Path(work_dir))
            if failures:
                raise failures.pop()
            yield Path(work_dir)

    with ExitStack() as stack:
        got = retry_on_transient_server_error(
            lambda: stack.enter_context(fetch()), sleep=lambda _s: None
        )
        assert len(made) == 2 and got == made[1]
        assert not made[0].exists() and made[1].is_dir()
    assert not made[1].exists()
