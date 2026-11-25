# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Hub API failure classifier
(:func:`~pitloom.extract.remote._hub_api.say_hub_failure`): which catalogued
``WARNING:`` each exception is said as (the order of its branches matters:
offline mode and a timeout are also :class:`OSError`), the timeout the line
names, an :class:`~pitloom.core.internal_error.InternalError` passed on
unsaid, the page URL a line names, and the failure text of a hostile server
(or ``HF_ENDPOINT``) on one masked line.

See also: tests/extract/remote/test_huggingface_api_timeout.py (a Hub that
never answers), tests/extract/remote/test_hub_loopback.py (a Hub that
answers with an error) and tests/messages/test_hub.py (the entries).
"""

from __future__ import annotations

import importlib
import json
import logging
import re
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from huggingface_hub import hf_raise_for_status
from huggingface_hub.errors import HfHubHTTPError, OfflineModeIsEnabled

from pitloom.core.internal_error import InternalError
from pitloom.extract.remote import _hub_api
from pitloom.extract.remote._hub_api import repo_page_url, say_hub_failure
from pitloom.extract.remote.huggingface_dataset import (
    DATASET_INFO_OUTCOME,
    _load_dataset_info,
)
from pitloom.extract.remote.huggingface_fetch import (
    MODEL_INFO_OUTCOME,
    _load_model_info,
)
from pitloom.logging_config import configure_logging
from pitloom.messages import MESSAGES, trusted_message
from pitloom.messages.network import (
    DOWNLOAD_FAILED,
    DOWNLOAD_TIMEOUT,
    HUB_RESPONSE_INVALID,
    OFFLINE_UNUSABLE,
)

pytestmark = pytest.mark.platform  # escapes, sockets' exception classes

_LOG = logging.getLogger("pitloom.test_hub_api")
_PAGE = "https://huggingface.co/o/m"
_OUTCOME = "x not recorded"
_TOKEN = "hf_" + "AbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGh"  # 34 letters


def _hub_http_error(message: str = "boom") -> HfHubHTTPError:
    """A real :class:`HfHubHTTPError`, its response one of the HTTP client
    ``huggingface_hub`` uses (``httpx`` from 1.0, ``httpx2`` in 2.x)."""
    client = importlib.import_module(
        HfHubHTTPError.__mro__[1].__module__.split(".", 1)[0]
    )
    request = client.Request("GET", "http://hub.invalid/api/models/o/m")
    build: Any = HfHubHTTPError
    error: HfHubHTTPError = build(
        message, response=client.Response(500, request=request)
    )
    return error


def _raised_for_status(headers: dict[str, str], status: int = 404) -> Exception:
    """What ``huggingface_hub`` raises for a *status* answer with *headers*,
    its response of the HTTP client the library uses."""
    client = importlib.import_module(
        HfHubHTTPError.__mro__[1].__module__.split(".", 1)[0]
    )
    request = client.Request("GET", "http://hub.invalid/api/models/o/m")
    response = client.Response(status, headers=headers, request=request, text="gone")
    with pytest.raises(HfHubHTTPError) as raised:
        hf_raise_for_status(response)
    return raised.value


def _client_error(client: str, name: str) -> Callable[[], Exception]:
    """A factory of the exception *name* of HTTP client *client*, skipping
    the test when the client is not installed."""

    def make() -> Exception:
        module = pytest.importorskip(client)
        cls: Any = getattr(module, name)
        return cls("t")  # type: ignore[no-any-return]

    return make


def _say(
    capsys: pytest.CaptureFixture[str],
    exc: Exception,
    *,
    url: str = _PAGE,
    outcome: str = _OUTCOME,
    seconds: float = 30.0,
) -> str:
    """The one line *exc* is said as, with its ``[code]``."""
    configure_logging()
    say_hub_failure(_LOG, exc, url=url, outcome=outcome, seconds=seconds)
    (line,) = capsys.readouterr().err.splitlines()
    return line


def _code(line: str) -> str:
    found = re.search(r" \[([a-z/-]+)\]$", line)
    assert found, line
    return found.group(1)


_BRANCHES = [
    (lambda: OfflineModeIsEnabled("offline"), OFFLINE_UNUSABLE),
    (lambda: TimeoutError("t"), DOWNLOAD_TIMEOUT),
    (_client_error("httpx2", "ReadTimeout"), DOWNLOAD_TIMEOUT),
    (_client_error("httpx", "ConnectTimeout"), DOWNLOAD_TIMEOUT),
    (_hub_http_error, DOWNLOAD_FAILED),
    (lambda: OSError(13, "Permission denied"), DOWNLOAD_FAILED),
    (lambda: ConnectionResetError("reset"), DOWNLOAD_FAILED),
    (_client_error("httpx2", "ConnectError"), DOWNLOAD_FAILED),
    (_client_error("httpx", "ConnectError"), DOWNLOAD_FAILED),
    (_client_error("httpx2", "TooManyRedirects"), DOWNLOAD_FAILED),
    (_client_error("httpx", "TooManyRedirects"), DOWNLOAD_FAILED),
    (lambda: json.JSONDecodeError("Expecting value", "<", 0), HUB_RESPONSE_INVALID),
    (lambda: ValueError("no"), HUB_RESPONSE_INVALID),
    (lambda: KeyError("id"), HUB_RESPONSE_INVALID),
    (lambda: TypeError("x"), HUB_RESPONSE_INVALID),
    (lambda: RuntimeError("boom"), HUB_RESPONSE_INVALID),
]
_BRANCH_IDS = [
    "offline",
    "timeout-builtin",
    "timeout-httpx2",
    "timeout-httpx",
    "http-error",
    "oserror",
    "connection-reset",
    "connect-httpx2",
    "connect-httpx",
    "redirects-httpx2",
    "redirects-httpx",
    "json",
    "value",
    "key",
    "type",
    "runtime",
]


@pytest.mark.parametrize(("make", "expected"), _BRANCHES, ids=_BRANCH_IDS)
def test_each_failure_is_said_as_the_entry_of_its_kind(
    capsys: pytest.CaptureFixture[str],
    make: Callable[[], Exception],
    expected: Any,
) -> None:
    line = _say(capsys, make())
    assert line.startswith(f"WARNING: URL={_PAGE}: ")
    assert _code(line) == expected.code
    assert line.endswith(f"; {_OUTCOME} [{expected.code}]") or (
        expected is OFFLINE_UNUSABLE
    )
    assert trusted_message(line) is MESSAGES[expected.code]


def test_offline_mode_is_checked_before_the_os_error_branch(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """:class:`OfflineModeIsEnabled` is a :class:`ConnectionError`, so an
    :class:`OSError`: the branch order alone tells it from a failed request."""
    assert issubclass(OfflineModeIsEnabled, OSError)
    assert _code(_say(capsys, OfflineModeIsEnabled("HF_HUB_OFFLINE"))) == (
        OFFLINE_UNUSABLE.code
    )
    assert _code(_say(capsys, ConnectionError("down"))) == DOWNLOAD_FAILED.code


def test_a_timeout_is_checked_before_the_os_error_branch(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The built-in :class:`TimeoutError` is an :class:`OSError` too."""
    assert issubclass(TimeoutError, OSError)
    assert _code(_say(capsys, TimeoutError("t"))) == DOWNLOAD_TIMEOUT.code
    assert _code(_say(capsys, OSError("t"))) == DOWNLOAD_FAILED.code


@pytest.mark.parametrize(
    ("seconds", "said"),
    [
        (0.5, "within 1 seconds"),
        (30.0, "within 30 seconds"),
        (29.2, "within 30 seconds"),
    ],
    ids=["half", "whole", "fraction"],
)
def test_a_timeout_names_the_seconds_the_request_was_given(
    capsys: pytest.CaptureFixture[str], seconds: float, said: str
) -> None:
    line = _say(capsys, TimeoutError("t"), seconds=seconds)
    assert f"no complete answer {said}; {_OUTCOME} [download-timeout]" in line


def test_the_offline_line_names_the_page_and_what_is_not_recorded(
    capsys: pytest.CaptureFixture[str],
) -> None:
    line = _say(capsys, OfflineModeIsEnabled("x"), outcome="licence not recorded")
    assert line.startswith(f"WARNING: URL={_PAGE}: ")
    assert "licence not recorded" in line and line.endswith("[offline-unusable]")


@pytest.mark.parametrize("header", ["x-request-id", "X-Amzn-Trace-Id", "x-amz-cf-id"])
def test_a_failed_request_is_said_alike_whatever_its_request_id(
    capsys: pytest.CaptureFixture[str], header: str
) -> None:
    """``huggingface_hub`` writes the response's request id into its text
    (``(Request ID: Root=...)``), new on every request: the line must be the
    same on every run."""
    first = _raised_for_status({header: "Root=1-659fc3fa-3031673e0f92c71a"})
    second = _raised_for_status({header: "Root=1-7a1b2c3d-00000000000000ff"})
    assert "Root=1-659fc3fa" in str(first) and str(first) != str(second)
    lines = [_say(capsys, first), _say(capsys, second)]
    assert lines[0] == lines[1] and "Root=" not in lines[0]
    assert _code(lines[0]) == DOWNLOAD_FAILED.code


def test_a_rate_limit_line_does_not_start_with_its_request_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A 429's text starts with a line break, so ``huggingface_hub`` writes
    the id first (``(Amz CF ID: ...) 429 ...``): dropping it leaves no space
    in front."""
    error = _raised_for_status({"X-Amz-Cf-Id": "cf-id-0123456789"}, status=429)
    assert str(error).startswith(" (Amz CF ID: cf-id-0123456789)")
    line = _say(capsys, error)
    assert line.startswith(f"WARNING: URL={_PAGE}: 429 Too Many Requests")
    assert ":  " not in line and "cf-id" not in line


def test_an_internal_error_is_passed_on_unsaid(
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = InternalError("a programming error")
    configure_logging()
    with pytest.raises(InternalError) as raised:
        say_hub_failure(_LOG, error, url=_PAGE, outcome=_OUTCOME, seconds=30.0)
    assert raised.value is error
    assert not capsys.readouterr().err


# -- the loaders pass an InternalError on, and say any other failure once -----


def _loader_cases() -> list[Any]:
    return [
        pytest.param(
            _load_model_info, "model_info", {}, MODEL_INFO_OUTCOME, id="model"
        ),
        pytest.param(
            _load_dataset_info, "dataset_info", None, DATASET_INFO_OUTCOME, id="dataset"
        ),
    ]


@pytest.mark.parametrize(
    ("loader", "request_name", "failed", "outcome"), _loader_cases()
)
def test_a_loader_passes_an_internal_error_on_as_it_is(
    caplog: pytest.LogCaptureFixture,
    loader: Callable[[str], Any],
    request_name: str,
    failed: object,
    outcome: str,
) -> None:
    """From the request itself, and from reading its answer."""
    _ = failed, outcome
    error = InternalError("contract broken")
    with patch(f"huggingface_hub.{request_name}", side_effect=error):
        with pytest.raises(InternalError) as raised:
            loader("o/m")
    assert raised.value is error

    answer = MagicMock()
    type(answer).author = property(lambda _self: (_ for _ in ()).throw(error))
    with patch(f"huggingface_hub.{request_name}", return_value=answer):
        with pytest.raises(InternalError) as raised:
            loader("o/m")
    assert raised.value is error
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize(
    ("loader", "request_name", "failed", "outcome"), _loader_cases()
)
@pytest.mark.parametrize(
    ("make", "expected"),
    [
        (lambda: RuntimeError("answer is no mapping"), HUB_RESPONSE_INVALID),
        (lambda: OfflineModeIsEnabled("off"), OFFLINE_UNUSABLE),
        (lambda: TimeoutError("t"), DOWNLOAD_TIMEOUT),
    ],
    ids=["invalid", "offline", "timeout"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_a_loader_says_any_other_failure_once_and_gives_the_empty_result(
    capsys: pytest.CaptureFixture[str],
    loader: Callable[[str], Any],
    request_name: str,
    failed: object,
    outcome: str,
    make: Callable[[], Exception],
    expected: Any,
) -> None:
    configure_logging()
    with patch(f"huggingface_hub.{request_name}", side_effect=make()):
        assert loader("o/m") == failed
    (line,) = capsys.readouterr().err.splitlines()
    assert _code(line) == expected.code
    assert outcome in line
    kind = "datasets/" if request_name == "dataset_info" else ""
    assert line.startswith(f"WARNING: URL=https://huggingface.co/{kind}o/m: ")


# -- the page a line names ----------------------------------------------------


@pytest.mark.parametrize(
    ("endpoint", "repo_type", "shown"),
    [
        ("https://huggingface.co", "model", "https://huggingface.co/o/m"),
        ("https://huggingface.co", "dataset", "https://huggingface.co/datasets/o/m"),
        ("https://mirror.example/hub/", "model", "https://mirror.example/hub/o/m"),
        ("https://u:s3cret@h.example", "model", "https://***:***@h.example/o/m"),
        ("https://h.example/\x1b[2J", "model", "'https://h.example/\\x1b[2J/o/m'"),
    ],
    ids=["model", "dataset", "mirror", "credentials", "escape"],
)
def test_the_page_is_on_the_hub_the_api_asks(
    monkeypatch: pytest.MonkeyPatch, endpoint: str, repo_type: str, shown: str
) -> None:
    monkeypatch.setattr(_hub_api, "hub_endpoint", lambda: endpoint)
    assert repo_page_url("o/m", repo_type) == shown


# -- a hostile server's text --------------------------------------------------

_HOSTILE = [
    (
        "bad\nWARNING: forged [over-cap]\x1b[2J",
        "'bad WARNING: forged [over-cap]\\x1b[2J'",
    ),
    ("tail [over-cap]", "tail [over-cap]"),
    (f"Bearer {_TOKEN}", "Bearer hf_***"),
    (f"ok\t{_TOKEN}", "ok hf_***"),
    ("see https://u:s3cret@h/x now", "see https://***:***@h/x now"),
]
_HOSTILE_IDS = ["newline-escape", "fake-code", "bearer", "tab", "url-user"]


def _shown(line: str) -> str:
    """The failure *line* writes: after ``URL=<page>: `` (inside the
    parentheses of the invalid-answer line), before ``; <outcome> [<code>]``."""
    text = line.removeprefix(f"WARNING: URL={_PAGE}: ")
    text = text.rsplit(f"; {_OUTCOME} [", 1)[0]
    prefix = "the Hub's answer could not be read ("
    return text.removeprefix(prefix).removesuffix(")") if prefix in text else text


@pytest.mark.parametrize(("hostile", "shown"), _HOSTILE, ids=_HOSTILE_IDS)
@pytest.mark.parametrize(
    ("make", "expected"),
    [
        (ValueError, HUB_RESPONSE_INVALID),
        (_hub_http_error, DOWNLOAD_FAILED),
    ],
    ids=["invalid", "http-error"],
)
def test_a_hostile_failure_is_one_masked_line_with_the_entrys_code(
    capsys: pytest.CaptureFixture[str],
    make: Callable[[str], Exception],
    expected: Any,
    hostile: str,
    shown: str,
) -> None:
    line = _say(capsys, make(hostile))
    assert _code(line) == expected.code
    assert trusted_message(line) is MESSAGES[expected.code]
    assert "s3cret" not in line and _TOKEN not in line and "\x1b" not in line
    assert _shown(line) == shown


def test_an_os_error_says_its_reason_not_its_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An :class:`OSError` with a reason is said by the reason alone (its
    text can quote a path), masked all the same."""
    line = _say(
        capsys,
        OSError(13, f"Denied\nERROR: forged {_TOKEN}", "/home/u/.cache/hf/x"),
    )
    assert "/home/u" not in line and _TOKEN not in line
    assert ": Denied ERROR: forged hf_***; " in line
    assert _code(line) == DOWNLOAD_FAILED.code


def test_a_hostile_endpoint_is_masked_in_the_page_of_a_line(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        _hub_api, "hub_endpoint", lambda: f"https://u:s3cret@h.example/\n{_TOKEN}"
    )
    page = repo_page_url("o/m")
    line = _say(capsys, ValueError("x"), url=page)
    assert "s3cret" not in line and "\n" not in line
    assert line.startswith("WARNING: URL='https://***:***@h.example/\\n")
