# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``tests/_network.py``: a network cause skips, anything else fails.

See also: tests/_network.py.
"""

from __future__ import annotations

import errno
import http.client
import ssl
import subprocess
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from email.message import Message
from pathlib import Path

import pytest

from tests._network import (
    REQUIRE_NETWORK_ENV,
    assert_spdx3_validate_ok,
    declares_network,
    network_strict,
    require_reachable,
    skip_if_network_failure,
    skip_on_network_error,
)
from tests._network_classify import network_cause_in_text, network_cause_of


@contextmanager
def _no_skip() -> Iterator[None]:
    """Fail, not skip, if the block skips: a wrongly skipping helper would
    otherwise turn an "expected to run" assertion into a silent skip."""
    try:
        yield
    except pytest.skip.Exception as exc:
        pytest.fail(f"unexpected skip: {exc}", pytrace=False)


@pytest.fixture(autouse=True)
def _lenient_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default to skip mode whatever the outer environment sets."""
    monkeypatch.delenv(REQUIRE_NETWORK_ENV, raising=False)


_SSL_TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "core.py", line 152, in load_validation_data\n'
    "urllib.error.URLError: <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING]"
    " EOF occurred in violation of protocol (_ssl.c:1006)>\n"
)


def _open_http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x.test/", code, "msg", Message(), None)


def _http_error(code: int) -> urllib.error.HTTPError:
    """A closed HTTPError: an unclosed one warns at GC on Python 3.14."""
    exc = _open_http_error(code)
    exc.close()
    return exc


@pytest.mark.parametrize(
    "text",
    [
        _SSL_TRACEBACK,
        "ERROR: fragment validate failed: <urlopen error Connection refused>",
        "ERROR: fragment validate failed: <urlopen error [Errno 61] refused>",
        "socket.gaierror: [Errno -2] Name or service not known",
        "ConnectionRefusedError: [Errno 61] Connection refused",
        "TimeoutError: timed out",
        "requests.exceptions.ConnectionError: Max retries exceeded with url",
    ],
)
def test_network_text_skips_with_cause(text: str) -> None:
    with pytest.raises(pytest.skip.Exception, match="network unavailable"):
        skip_if_network_failure(text)


def test_network_text_cause_is_last_matching_line() -> None:
    cause = network_cause_in_text(_SSL_TRACEBACK)
    assert cause is not None
    assert cause.startswith("urllib.error.URLError")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "jsonschema.exceptions.ValidationError: 'x' is a required property",
        "ERROR: [shacl] Constraint Violation in MinCountConstraintComponent",
        # a finding that quotes network-sounding data
        'ERROR:   Value Node: Literal("Request timed out")',
        "ERROR: (merged): [schema] 'SSL: foo' is not of type 'integer'",
        # prose, not an exception line
        "the element name ConnectionError handler is documented",
        "WARNING: retry after the request timed out",
        # a real-looking network line beside a finding: the finding wins
        "ERROR: [shacl] Violation\nERROR: \tFocus Node: _:x\n" + _SSL_TRACEBACK,
    ],
)
def test_non_network_text_does_not_skip(text: str) -> None:
    assert network_cause_in_text(text) is None
    with _no_skip():
        skip_if_network_failure(text)  # returns normally


@pytest.mark.parametrize(
    "exc",
    [
        urllib.error.URLError("boom"),
        ssl.SSLError("handshake"),
        ConnectionResetError("reset"),
        TimeoutError("slow"),
        _http_error(503),
        _http_error(429),
    ],
)
def test_network_exception_skips(exc: Exception) -> None:
    with pytest.raises(pytest.skip.Exception, match="network unavailable"):
        with skip_on_network_error():
            raise exc


def test_network_cause_found_through_value_error_chain() -> None:
    def fetch() -> None:
        try:
            raise urllib.error.URLError("dns")
        except OSError as inner:
            raise ValueError("Cannot read source") from inner

    with pytest.raises(pytest.skip.Exception, match="dns"):
        with skip_on_network_error():
            fetch()


def test_suppressed_context_is_not_walked() -> None:
    def fetch() -> None:
        try:
            raise TimeoutError("slow")
        except TimeoutError:
            raise ValueError("bad json") from None

    with pytest.raises(ValueError):
        with _no_skip(), skip_on_network_error():
            fetch()


def _raise_wrapped() -> None:
    raise ValueError("wrapped")


def test_implicit_context_is_walked() -> None:
    with pytest.raises(ValueError) as caught:
        try:
            raise TimeoutError("slow")
        except TimeoutError:
            _raise_wrapped()
    assert network_cause_of(caught.value) is not None


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("bad json"),
        _http_error(404),
        KeyError("k"),
        http.client.InvalidURL("nonnumeric port"),
        urllib.error.URLError("unknown url type: foo"),
        urllib.error.URLError(FileNotFoundError("no such file")),
    ],
)
def test_non_network_exception_propagates(exc: Exception) -> None:
    with pytest.raises(type(exc)):
        with _no_skip(), skip_on_network_error():
            raise exc


def test_url_error_with_network_reason_skips() -> None:
    with pytest.raises(pytest.skip.Exception, match="network unavailable"):
        with skip_on_network_error():
            raise urllib.error.URLError(ConnectionRefusedError("refused"))


def _fake_run(returncode: int, stderr: str) -> object:
    def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], returncode, stdout="", stderr=stderr)

    return run


def test_spdx3_validate_network_failure_skips(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("tests._network.subprocess.run", _fake_run(1, _SSL_TRACEBACK))
    with pytest.raises(pytest.skip.Exception, match="network unavailable"):
        assert_spdx3_validate_ok(tmp_path / "sbom.json")


def test_spdx3_validate_real_failure_still_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = "ERROR: [shacl] Constraint Violation\n"
    monkeypatch.setattr("tests._network.subprocess.run", _fake_run(1, stderr))
    with pytest.raises(AssertionError, match="spdx3-validate failed"):
        with _no_skip():
            assert_spdx3_validate_ok(tmp_path / "sbom.json")


def test_spdx3_validate_success_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("tests._network.subprocess.run", _fake_run(0, ""))
    with _no_skip():
        assert_spdx3_validate_ok(tmp_path / "sbom.json")


def test_spdx3_validate_success_ignores_network_looking_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Stderr is scanned only for a failed run, never on returncode 0."""
    monkeypatch.setattr("tests._network.subprocess.run", _fake_run(0, _SSL_TRACEBACK))
    with _no_skip():
        assert_spdx3_validate_ok(tmp_path / "sbom.json")


def _fake_urlopen(outcomes: dict[str, Exception | None], probed: list[str]) -> object:
    def urlopen(request: urllib.request.Request, **_kwargs: object) -> object:
        probed.append(request.full_url)
        outcome = outcomes.get(request.full_url)
        if outcome is not None:
            raise outcome
        return nullcontext()

    return urlopen


def test_require_reachable_skips_on_unreachable_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probed: list[str] = []
    outcomes: dict[str, Exception | None] = {"https://x.test/": _url_refused()}
    monkeypatch.setattr(
        "tests._network.urllib.request.urlopen", _fake_urlopen(outcomes, probed)
    )
    with pytest.raises(pytest.skip.Exception, match="refused"):
        require_reachable("https://x.test/")


def test_require_reachable_probes_every_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probed: list[str] = []
    outcomes: dict[str, Exception | None] = {"https://b.test/": _url_refused()}
    monkeypatch.setattr(
        "tests._network.urllib.request.urlopen", _fake_urlopen(outcomes, probed)
    )
    with pytest.raises(pytest.skip.Exception, match="refused"):
        require_reachable("https://a.test/", "https://b.test/")
    assert probed == ["https://a.test/", "https://b.test/"]


@pytest.mark.parametrize("code", [200, 404])
def test_require_reachable_accepts_any_answer_below_429(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    outcomes: dict[str, Exception | None] = {
        "https://x.test/": None if code == 200 else _http_error(code)
    }
    monkeypatch.setattr(
        "tests._network.urllib.request.urlopen", _fake_urlopen(outcomes, [])
    )
    with _no_skip():
        require_reachable("https://x.test/")


def test_require_reachable_skips_on_transient_http_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcomes: dict[str, Exception | None] = {"https://x.test/": _http_error(503)}
    monkeypatch.setattr(
        "tests._network.urllib.request.urlopen", _fake_urlopen(outcomes, [])
    )
    with pytest.raises(pytest.skip.Exception, match="network unavailable"):
        require_reachable("https://x.test/")


@pytest.mark.parametrize("code", [404, 503])
def test_require_reachable_closes_http_error(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    error = _open_http_error(code)
    monkeypatch.setattr(
        "tests._network.urllib.request.urlopen",
        _fake_urlopen({"https://x.test/": error}, []),
    )
    with pytest.raises(pytest.skip.Exception) if code >= 500 else _no_skip():
        require_reachable("https://x.test/")
    assert error.fp.closed


def _url_refused() -> urllib.error.URLError:
    return urllib.error.URLError("refused")


@pytest.mark.parametrize("value", ["1", "true", "YES", " on "])
def test_strict_mode_fails_instead_of_skipping_on_text(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(REQUIRE_NETWORK_ENV, value)
    with pytest.raises(pytest.fail.Exception, match="URLError"):
        with _no_skip():
            skip_if_network_failure(_SSL_TRACEBACK)


def test_strict_mode_fails_instead_of_skipping_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(REQUIRE_NETWORK_ENV, "1")
    with pytest.raises(pytest.fail.Exception, match="refused"):
        with _no_skip(), skip_on_network_error():
            raise urllib.error.URLError("refused")


def test_strict_mode_fails_spdx3_validate_network_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(REQUIRE_NETWORK_ENV, "1")
    monkeypatch.setattr("tests._network.subprocess.run", _fake_run(1, _SSL_TRACEBACK))
    with pytest.raises(pytest.fail.Exception, match="network unavailable"):
        with _no_skip():
            assert_spdx3_validate_ok(tmp_path / "sbom.json")


@pytest.mark.parametrize("value", ["", "0", "false", "No", "off"])
def test_strict_mode_off_values_still_skip(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(REQUIRE_NETWORK_ENV, value)
    assert network_strict() is False
    with pytest.raises(pytest.skip.Exception):
        skip_if_network_failure(_SSL_TRACEBACK)


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE"])
def test_strict_mode_on_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(REQUIRE_NETWORK_ENV, value)
    assert network_strict() is True


@pytest.mark.parametrize("value", ["2", "maybe", "enable", "y"])
def test_strict_mode_unknown_value_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(REQUIRE_NETWORK_ENV, value)
    with pytest.raises(pytest.UsageError, match=REQUIRE_NETWORK_ENV):
        network_strict()


def test_strict_mode_does_not_change_non_network_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(REQUIRE_NETWORK_ENV, "1")
    with _no_skip():
        skip_if_network_failure("ERROR: [shacl] Constraint Violation")  # no raise
    with pytest.raises(ValueError):
        with _no_skip(), skip_on_network_error():
            raise ValueError("bad json")


@pytest.mark.parametrize(
    "text",
    [
        "urllib.error.HTTPError: HTTP Error 503: Service Unavailable",
        "urllib.error.HTTPError: HTTP Error 429: Too Many Requests",
        "urllib.error.HTTPError: HTTP Error 502: Bad Gateway",
        "urllib.error.HTTPError: HTTP Error 504: Gateway Timeout",
        "ConnectionResetError: [Errno 54] Connection reset by peer",
        "http.client.IncompleteRead: IncompleteRead(0 bytes read)",
        "TimeoutError: The read operation timed out",
        "socket.timeout: The read operation timed out",
        "ConnectionResetError: [WinError 10054] An existing connection was closed",
        "ConnectionRefusedError: [WinError 10061] No connection could be made",
        "socket.gaierror: [Errno 11001] getaddrinfo failed",
        "ERROR: fragment validate failed: HTTP Error 503: Service Unavailable",
        "ERROR: fragment validate failed: <urlopen error [WinError 10065] x>",
        "ERROR: fetch failed: [Errno 54] Connection reset by peer",
    ],
)
def test_more_network_text_shapes_skip(text: str) -> None:
    assert network_cause_in_text(text) is not None
    with pytest.raises(pytest.skip.Exception, match="network unavailable"):
        skip_if_network_failure(text)


@pytest.mark.parametrize(
    "text",
    [
        "urllib.error.HTTPError: HTTP Error 404: Not Found",
        "urllib.error.HTTPError: HTTP Error 403: Forbidden",
        "ERROR: fragment validate failed: HTTP Error 404: Not Found",
        "ERROR: fragment validate failed: 'name' is a required property",
        "OSError: [Errno 2] No such file or directory: 'x'",
    ],
)
def test_more_non_network_text_shapes_do_not_skip(text: str) -> None:
    assert network_cause_in_text(text) is None


@pytest.mark.parametrize(
    "exc",
    [
        OSError(errno.ENETUNREACH, "Network is unreachable"),
        OSError(errno.EHOSTUNREACH, "No route to host"),
        OSError(errno.ECONNRESET, "reset"),
        OSError(errno.ETIMEDOUT, "timed out"),
        urllib.error.URLError(OSError(errno.ENETUNREACH, "unreachable")),
        urllib.error.URLError(OSError(errno.EHOSTUNREACH, "no route")),
        http.client.IncompleteRead(b"ab", 5),
        http.client.RemoteDisconnected("closed"),
        _http_error(500),
        _http_error(504),
    ],
)
def test_more_network_exception_shapes_skip(exc: Exception) -> None:
    assert network_cause_of(exc) is not None
    with pytest.raises(pytest.skip.Exception, match="network unavailable"):
        with skip_on_network_error():
            raise exc


def _winerror(code: int) -> OSError:
    exc = OSError(0, "winsock")
    exc.winerror = code  # type: ignore[attr-defined]
    return exc


@pytest.mark.parametrize("code", [10051, 10054, 10060, 10061, 10065, 11001])
def test_winerror_codes_are_network(code: int) -> None:
    assert network_cause_of(_winerror(code)) is not None
    assert network_cause_of(urllib.error.URLError(_winerror(code))) is not None


@pytest.mark.parametrize(
    "exc",
    [
        OSError(errno.ENOENT, "No such file"),
        OSError(errno.EACCES, "denied"),
        OSError("no errno"),
        _winerror(5),
        _http_error(400),
        _http_error(403),
        urllib.error.URLError(OSError(errno.ENOENT, "No such file")),
    ],
)
def test_more_non_network_exception_shapes_propagate(exc: Exception) -> None:
    assert network_cause_of(exc) is None


@pytest.mark.parametrize(
    "source, expected",
    [
        ("@pytest.mark.network\ndef test_a(): ...", True),
        ("from pytest import mark\n@mark.network\ndef test_a(): ...", True),
        ("pytestmark = pytest.mark.network", True),
        ("def test_a(): ...", False),
        ("# networking notes", False),
    ],
)
def test_declares_network_spellings(
    tmp_path: Path, source: str, expected: bool
) -> None:
    path = tmp_path / "test_x.py"
    path.write_text(source, encoding="utf-8")
    assert declares_network(path) is expected
