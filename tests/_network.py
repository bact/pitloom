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

See also: tests/_network_classify.py (classification),
tests/test_network_helpers.py (the helpers' own tests).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NoReturn

import pytest

from tests._network_classify import network_cause_in_text, network_cause_of

#: Environment variable that turns a network-caused skip into a failure.
REQUIRE_NETWORK_ENV = "PITLOOM_REQUIRE_NETWORK"

_STRICT_VALUES = frozenset({"1", "true", "yes", "on"})
_LENIENT_VALUES = frozenset({"", "0", "false", "no", "off"})


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
    config.pluginmanager.register(_DirectoryGate(), "pitloom-network-directory-gate")


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
    its source mentions ``pytest.mark.network``. A directory skipped by its
    ``conftest.py`` is handled by :class:`_DirectoryGate`.
    """
    outcome: Any = yield
    _fail_skipped_collect(collector, outcome.get_result())


class _DirectoryGate:
    """Same gate for a directory skipped by its own ``conftest.py``.

    That skipped report is produced by a hook proxy that omits the parent
    ``conftest.py``'s hooks, so it is registered as a plugin instead.
    """

    @pytest.hookimpl(hookwrapper=True)
    def pytest_make_collect_report(self, collector: pytest.Collector) -> Iterator[None]:
        """Fail a skipped directory holding a network-marked ``.py`` file."""
        outcome: Any = yield
        if isinstance(collector, pytest.Directory):
            _fail_skipped_collect(collector, outcome.get_result())


def _fail_skipped_collect(collector: pytest.Collector, report: Any) -> None:
    if not report.skipped or not collector.config.stash.get(_STRICT_KEY, False):
        return
    if not _declares_network_node(collector):
        return
    longrepr = report.longrepr
    reason = longrepr[2] if isinstance(longrepr, tuple) else str(longrepr)
    report.outcome = "failed"
    report.longrepr = (
        f"network module skipped ({REQUIRE_NETWORK_ENV} set, skips not allowed): "
        f"{reason}"
    )


def _declares_network_node(collector: pytest.Collector) -> bool:
    """Whether a skipped module or directory *collector* holds network tests."""
    if isinstance(collector, pytest.Module):
        return declares_network(collector.path)
    if isinstance(collector, pytest.Directory):
        return any(declares_network(p) for p in sorted(collector.path.rglob("*.py")))
    return False


_NETWORK_MARK = re.compile(r"\bmark\.network\b")


def declares_network(path: Path) -> bool:
    """Whether the module at *path* mentions ``mark.network`` (any spelling)."""
    try:
        return _NETWORK_MARK.search(path.read_text(encoding="utf-8")) is not None
    except (OSError, UnicodeDecodeError):
        return False
