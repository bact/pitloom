# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Turn a network-caused test failure into a skip that names the cause.

Tests marked ``@pytest.mark.network`` reach a real remote host -- directly
(``urllib``) or through a subprocess or library (``spdx3-validate`` downloads
the SPDX JSON Schema and SHACL model on every run, with no offline mode).
``tests/conftest.py``'s socket block does not cover a subprocess, and a live
host can fail for reasons unrelated to Pitloom (TLS handshake, DNS, timeout).
These helpers skip on such a failure and let any other failure through, so a
flaky network neither turns CI red nor hides a real regression.

Setting ``PITLOOM_REQUIRE_NETWORK`` to a true value makes the same network
failure a test *failure* naming the cause instead, and turns any skipped
``network`` test into a failure (``pytest_runtest_makereport`` and
``pytest_make_collect_report`` below, wired into ``tests/conftest.py``): the
release workflow (``.github/workflows/pypi-publish.yml``) sets it so an unreachable host
blocks publishing rather than being skipped. Accepted values (case-
insensitive): ``1``/``true``/``yes``/``on`` strict; unset/empty/``0``/
``false``/``no``/``off`` lenient. Any other value is a usage error.

See also: tests/test_network_helpers.py (the helpers' own tests).
"""

from __future__ import annotations

import http.client
import os
import re
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NoReturn

import pytest

#: Environment variable that turns a network-caused skip into a failure.
REQUIRE_NETWORK_ENV = "PITLOOM_REQUIRE_NETWORK"

_STRICT_VALUES = frozenset({"1", "true", "yes", "on"})
_LENIENT_VALUES = frozenset({"", "0", "false", "no", "off"})

# Message signatures of a network cause.
_NETWORK_TEXT = re.compile(
    r"urlopen error|URLError|SSLError|SSL:|CERTIFICATE_VERIFY|ConnectionError|"
    r"Connection (?:refused|reset|aborted)|ProxyError|Max retries exceeded|"
    r"Failed to establish a new connection|timed out|TimeoutError|"
    r"Name or service not known|nodename nor servname|"
    r"Temporary failure in name resolution|Network is unreachable|gaierror|"
    r"RemoteDisconnected|IncompleteRead|"
    r"Could not find a version that satisfies|No matching distribution",
    re.IGNORECASE,
)

# A traceback tail: ``pkg.mod.SomeError: message`` (not the CLI's ``ERROR:``).
_EXCEPTION_LINE = re.compile(
    r"^\s*(?:[\w.]+\.)?\w*(?:Error|Exception|gaierror|Disconnected): "
)
# The CLI's ``ERROR: ...`` shape for a network failure it wrapped.
_CLI_NETWORK_LINE = re.compile(
    r"^ERROR:\s.*(?:<urlopen error|Could not find a version that satisfies|"
    r"No matching distribution)"
)
# A validator finding: its message quotes data and may contain any words.
_VALIDATION_FINDING = re.compile(
    r"\[(?:shacl|schema)\]|Value Node:|Focus Node:", re.IGNORECASE
)

# ``URLError`` reasons (plain strings) that are a malformed URL, not the network.
_URL_ERROR_LOCAL_REASONS = ("unknown url type", "no host given", "file not on local")

_NETWORK_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    socket.timeout,
    socket.gaierror,
    ssl.SSLError,
    http.client.HTTPException,
    urllib.error.URLError,
)


def network_strict() -> bool:
    """Return whether ``PITLOOM_REQUIRE_NETWORK`` asks for strict mode.

    Raises:
        pytest.UsageError: the value is neither a true nor a false spelling.
    """
    raw = os.environ.get(REQUIRE_NETWORK_ENV, "")
    value = raw.strip().lower()
    if value in _STRICT_VALUES:
        return True
    if value in _LENIENT_VALUES:
        return False
    raise pytest.UsageError(
        f"{REQUIRE_NETWORK_ENV}={raw!r} is not a boolean; use one of "
        f"{sorted(_STRICT_VALUES)} or {sorted(_LENIENT_VALUES - {''})}"
    )


def network_cause_in_text(text: str) -> str | None:
    """Return the last exception line of *text* naming a network failure.

    Only traceback-tail and CLI ``ERROR:`` lines count, and never text that
    contains a validator finding (``[shacl]``/``[schema]``, ``Value Node:``):
    a finding quotes arbitrary data such as ``Request timed out``.
    """
    if _VALIDATION_FINDING.search(text):
        return None
    matches = [
        ln.strip()
        for ln in text.splitlines()
        if (_EXCEPTION_LINE.match(ln) or _CLI_NETWORK_LINE.match(ln))
        and _NETWORK_TEXT.search(ln)
    ]
    return matches[-1] if matches else None


def _is_network_exception(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or exc.code >= 500
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, BaseException):
            return _is_network_exception(reason)
        return not str(reason).startswith(_URL_ERROR_LOCAL_REASONS)
    if isinstance(exc, http.client.InvalidURL):
        return False
    return isinstance(exc, _NETWORK_EXCEPTIONS)


def network_cause_of(exc: BaseException) -> str | None:
    """Return a description if *exc* (or its cause chain) is a network failure.

    An HTTP error status counts only when transient (429 or 5xx); a 4xx is
    a real answer and stays a failure. A malformed URL is not the network.
    The walk follows ``__cause__``, then ``__context__`` unless
    ``raise ... from None`` suppressed it.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if _is_network_exception(cur):
            return f"{type(cur).__name__}: {cur}"
        if cur.__cause__ is not None:
            cur = cur.__cause__
        else:
            cur = None if cur.__suppress_context__ else cur.__context__
    return None


def _network_unavailable(cause: str) -> NoReturn:
    """Skip the test for a network *cause*; fail it in strict mode."""
    if network_strict():
        pytest.fail(f"network unavailable ({REQUIRE_NETWORK_ENV} set): {cause}")
    pytest.skip(f"network unavailable: {cause}")


def skip_if_network_failure(text: str) -> None:
    """Skip the test if captured *text* shows a network failure."""
    cause = network_cause_in_text(text)
    if cause is not None:
        _network_unavailable(cause)


@contextmanager
def skip_on_network_error() -> Iterator[None]:
    """Skip the test if the block raises a network-caused exception."""
    try:
        yield
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        cause = network_cause_of(exc)
        if cause is None:
            raise
        _network_unavailable(cause)


def require_reachable(*urls: str) -> None:
    """Skip the test unless every URL in *urls* answers (a cheap probe).

    For code that swallows a network failure and reports only a generic
    error, so the cause cannot be recognised after the fact. Any HTTP
    answer below 429/500 (even a 404) shows the host is reachable.
    """
    for url in urls:
        with skip_on_network_error():
            request = urllib.request.Request(url, method="HEAD")
            try:
                # URL is a fixed https literal from the calling test.
                with urllib.request.urlopen(request, timeout=10.0):  # nosec B310
                    pass
            except urllib.error.HTTPError as exc:
                if exc.code == 429 or exc.code >= 500:
                    raise


_VALIDATE_ARGV = (
    "-c",
    "import sys; from spdx3_validate.main import main; sys.exit(main())",
)


def assert_spdx3_validate_ok(sbom_file: Path) -> None:
    """Run spdx3-validate on *sbom_file*; assert it passes.

    Runs the console script's entry point, not ``-m spdx3_validate``:
    spdx3-validate 0.0.7's ``__main__`` drops ``main()``'s return code, so
    ``-m`` exits 0 on an invalid document. Skips when the run failed because
    it could not download the schema.
    """
    res = subprocess.run(
        [sys.executable, *_VALIDATE_ARGV, "--json", str(sbom_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        skip_if_network_failure(res.stderr)
    assert res.returncode == 0, f"spdx3-validate failed: {res.stderr} {res.stdout}"


_STRICT_KEY: pytest.StashKey[bool] = pytest.StashKey()


def pytest_configure(config: pytest.Config) -> None:
    """Read ``PITLOOM_REQUIRE_NETWORK`` once, before any test runs.

    A malformed value is a usage error. The hooks below use this stored value,
    so a test that edits the environment cannot switch the gate off.
    """
    config.stash[_STRICT_KEY] = network_strict()


def fail_skipped_network_test(item: pytest.Item, report: pytest.TestReport) -> None:
    """In strict mode, turn a skipped ``network`` test's *report* into a failure.

    Covers every skip route (``importorskip``, a missing sdist, a helper):
    the release gate must not pass with its network tests unrun.
    """
    if not report.skipped or hasattr(report, "wasxfail"):
        return
    if not item.config.stash.get(_STRICT_KEY, False):
        return
    if item.get_closest_marker("network") is None:
        return
    longrepr = report.longrepr
    reason = longrepr[2] if isinstance(longrepr, tuple) else str(longrepr)
    report.outcome = "failed"
    report.longrepr = (
        f"network test skipped ({REQUIRE_NETWORK_ENV} set, skips not allowed): {reason}"
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Iterator[None]:
    """Apply :func:`fail_skipped_network_test` to every phase's report."""
    del call
    outcome: Any = yield
    fail_skipped_network_test(item, outcome.get_result())


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector: pytest.Collector) -> Iterator[None]:
    """In strict mode, fail a module skipped at import that uses the marker.

    A module-level ``importorskip`` or ``skip(allow_module_level=True)``
    yields a skipped collect report, which ``pytest_runtest_makereport``
    never sees. No items exist, so a module counts as a network module when
    its source mentions ``pytest.mark.network``.
    """
    outcome: Any = yield
    report = outcome.get_result()
    if not report.skipped or not collector.config.stash.get(_STRICT_KEY, False):
        return
    if not isinstance(collector, pytest.Module) or not _declares_network(
        collector.path
    ):
        return
    longrepr = report.longrepr
    reason = longrepr[2] if isinstance(longrepr, tuple) else str(longrepr)
    report.outcome = "failed"
    report.longrepr = (
        f"network module skipped ({REQUIRE_NETWORK_ENV} set, skips not allowed): "
        f"{reason}"
    )


def _declares_network(path: Path) -> bool:
    """Whether the test module at *path* mentions ``pytest.mark.network``."""
    try:
        return "pytest.mark.network" in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
