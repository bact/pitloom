# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared pytest fixtures and configuration."""

import functools
import ipaddress
import json
import logging
import os
import socket
import sys
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from pitloom import logging_config
from pitloom.extract._license import clear_resolution_cache
from pitloom.extract._license_text_match import _get_detector
from pitloom.logging_config import _WARNED_ONCE
from pitloom.messages import strict_surfaces
from tests._environ import environ_restored
from tests._logger_state import pitloom_logger_unconfigured
from tests._message_drift import record_problem

# pylint: disable-next=unused-import
from tests._network import (  # noqa: F401
    bypass_proxies,
    fail_skipped_network_test,
    pytest_configure,
    pytest_make_collect_report,
)
from tests._platform import is_platform_file
from tests._spdx3_validate import use_offline_model
from tests._strict_uncoded import (
    MARKER,
    Finding,
    FixtureWatch,
    call_ran,
    failures,
    line_finding,
    note_call_report,
    strict_finding,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

#: The log record factory before any test, which every test starts and ends
#: with (`_restore_pitloom_logger`).
_RECORD_FACTORY = logging.getLogRecordFactory()

#: Longest test node id allowed. pytest puts the id in the
#: PYTEST_CURRENT_TEST environment variable, which Windows caps at 32,767
#: characters: a long parametrize value needs a short explicit ``ids=``.
MAX_NODEID_LENGTH = 1000

#: The strict check over wider fixtures (``pytest_fixture_setup``), hooked
#: here, before any test patches ``Logger.handle``, so a per-test patch
#: always wraps it and its undoing never drops it.
_FIXTURE_WATCH = FixtureWatch()
_FIXTURE_WATCH.install()


@pytest.fixture(autouse=True)
def _short_nodeid(request: pytest.FixtureRequest) -> None:
    """Fail any test whose node id is over :data:`MAX_NODEID_LENGTH`, on
    every platform, not only where the environment variable overflows. A
    fixture, not a collection hook: xdist drops the message of an
    exception raised in ``pytest_collection_modifyitems``."""
    if len(request.node.nodeid) > MAX_NODEID_LENGTH:
        pytest.fail(
            f"node id over {MAX_NODEID_LENGTH} characters;"
            " give the parametrize a short ids=",
            pytrace=False,
        )


def _assert_no_duplicate_spdx_ids(
    sbom_json: str | None = None, exporter: Any | None = None
) -> None:
    """Assert no two elements share a ``spdxId``.

    Pass *exporter* (a :class:`~pitloom.export.spdx3_json.Spdx3JsonExporter`)
    whenever the caller has one: checking its ``object_set`` directly is
    the strict form, since Pitloom's own ``_deduplicate_named_elements``
    (``pitloom.export.spdx3_json``) silently drops a later same-id element
    from the *serialised* ``@graph`` whenever its fields are byte-for-byte
    identical to an earlier one -- which can mask a genuine duplicate id
    on two elements that happen to carry identical content (e.g. two
    same-fallback-name AI model packages). Pass *sbom_json* (the
    generator's own returned string) instead when no exporter is
    reachable, e.g. a test that only calls a public
    ``generate_*_sbom()``/CLI entry point.
    """
    if exporter is not None:
        ids = [
            str(obj.spdxId)
            for obj in exporter.object_set.objects
            if getattr(obj, "spdxId", None)
        ]
    else:
        assert sbom_json is not None, "pass sbom_json or exporter"
        graph = json.loads(sbom_json)["@graph"]
        ids = [e["spdxId"] for e in graph if "spdxId" in e]
    assert len(ids) == len(set(ids)), f"duplicate spdxId: {sorted(ids)}"


def fake_build_and_read_path(*parts: str) -> str:
    """A path string that mimics ``--allow-build``'s fresh
    ``tempfile.mkdtemp()`` extraction directory (see
    ``ProjectFile.physical_path``'s docstring): genuinely absolute
    under the current platform's own :mod:`pathlib` semantics, never
    project-relative.

    A hardcoded POSIX literal such as ``"/tmp/xyz"`` is *not* absolute
    under ``WindowsPath`` semantics (``is_absolute()`` requires a drive
    letter there) -- using one silently stops exercising the
    absolute-``physical_path`` branch under test on Windows CI, even
    though the equivalent real value (from a real ``tempfile.mkdtemp()``
    on Windows) always carries a drive letter and is genuinely absolute.
    """
    return Path(tempfile.gettempdir(), "pitloom-build-and-read-fake", *parts).as_posix()


class _NetworkBlockedError(RuntimeError):
    """Raised when a test tries to open a real network socket."""


def _blocked_socket(*_args: Any, **_kwargs: Any) -> None:
    raise _NetworkBlockedError(
        "Real network access attempted during a test. Mock the network call "
        "(e.g. patch urllib.request.urlopen / fetch_json), or opt in "
        "explicitly with @pytest.mark.network if the test genuinely "
        "needs a live socket."
    )


def _is_local(host: str) -> bool:
    """Whether *host* is this machine: ``localhost`` or a loopback address."""
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return address.is_loopback or bool(mapped and mapped.is_loopback)


def _loopback_only(real_connect: Callable[..., Any]) -> Callable[..., Any]:
    """*real_connect* that refuses an address other than this machine's.

    The refused socket is closed before the error is raised:
    ``socket.create_connection`` closes its socket on an ``OSError`` only, so
    this error would leave it open, and Python reports it (a
    ``ResourceWarning``) in whichever test runs when it is freed.
    """

    def connect(self: socket.socket, address: Any, *args: Any) -> Any:
        host = address[0] if isinstance(address, tuple) else None
        if isinstance(host, str) and not _is_local(host):
            self.close()
            raise _NetworkBlockedError(
                f"A loopback test reached {host!r}. Use only a local server, or "
                "mark the test @pytest.mark.network if it needs a real host."
            )
        return real_connect(self, address, *args)

    return connect


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture(autouse=True)
def _reset_license_matcher_cache() -> None:
    """Clear the cached ``LicenseDetector`` and the declared-value answers
    before each test, so a mock from one test can't leak into the next via
    ``_get_detector``'s cache or the resolution cache."""
    _get_detector.cache_clear()
    clear_resolution_cache()


@pytest.fixture(autouse=True)
def _strict_surfaces() -> Iterator[None]:
    """Fail a test in which the Hatchling hook says a line it was ruled
    unable to reach (:meth:`pitloom.messages.Twins.no_hook`): outside the
    suite the library's wording is said instead."""
    with strict_surfaces():
        yield


@pytest.fixture(autouse=True)
def _reset_warn_once_state() -> None:
    """Clear ``log_once()``'s (and ``warn_once()``'s) per-process dedup state
    before each test, so one test's downgrade to DEBUG can't leak into the
    next."""
    _WARNED_ONCE.clear()


@pytest.fixture(autouse=True)
def _restore_pitloom_logger() -> Iterator[None]:
    """Start and end each test with the ``pitloom`` logger unconfigured.

    A fixed state, not a snapshot taken when the test starts: a module- or
    session-scoped fixture that calls ``configure_logging()`` runs before
    this one, and a snapshot would keep its level and handler for every
    later test on the worker (see :mod:`tests._logger_state`).
    The log record factory is reset alike: the first
    ``configure_logging()`` on a worker installs a masking one, process wide.
    """
    logging.setLogRecordFactory(_RECORD_FACTORY)
    try:
        with pitloom_logger_unconfigured():
            yield
    finally:
        logging.setLogRecordFactory(_RECORD_FACTORY)


@pytest.fixture(autouse=True)
def _catalogued_records_are_valid(request: pytest.FixtureRequest) -> Iterator[None]:
    """Fail a test during which any log record carried a ``pitloom_code``
    that is uncatalogued, at a level or with a text its entry does not say
    (:func:`tests._message_drift.record_problem`), or Pitloom said a record
    or an ``ERROR:`` line without a code that its kind does not explain and
    no ``uncoded_output`` marker of the test allows (:mod:`tests
    ._strict_uncoded`). Hooked on ``Logger.handle`` so every record counts,
    whatever the handlers, and on ``print_error``'s one seam
    ``_write_error_line``; the hooks are their own patch, undone at the end
    without touching the test's ``monkeypatch``. A logger named
    ``pitloom.test_*`` is a test's own and is not checked. An uncoded line
    said while a wider fixture's window is open (one the test sets up with
    ``request.getfixturevalue``) is that window's to report, not this
    check's."""
    problems: list[str] = []
    findings: list[Finding] = []
    handle = logging.Logger.handle
    # pylint: disable-next=protected-access
    write = logging_config._write_error_line

    def watching(self: logging.Logger, record: logging.LogRecord) -> None:
        problem = record_problem(record)
        if problem is not None:
            finding = strict_finding(record)
            if finding is None:
                problems.append(problem)
            elif not _FIXTURE_WATCH.watching:
                findings.append(finding)
        handle(self, record)

    def watching_lines(line: str) -> None:
        finding = line_finding(line)
        if finding is not None and not _FIXTURE_WATCH.watching:
            findings.append(finding)
        write(line)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(logging.Logger, "handle", watching)
        patch.setattr(logging_config, "_write_error_line", watching_lines)
        yield
    allowances = [
        pattern
        for mark in request.node.own_markers
        if mark.name == MARKER
        for pattern in mark.args
    ]
    problems = [f"catalogued record: {p}" for p in problems]
    unallowed = failures(findings, allowances, ran=call_ran(request.node))
    problems += [f"uncoded output: {f}" for f in unallowed]
    if problems:
        pytest.fail("; ".join(problems), pytrace=False)


@pytest.fixture(autouse=True)
def _restore_environ() -> Iterator[None]:
    """Put ``os.environ`` back after each test (see :mod:`tests._environ`)."""
    with environ_restored():
        yield


def _sboms_in(root: str) -> set[str]:
    """``*.spdx3.json`` in *root* (``os.listdir``: a test may patch ``Path``)."""
    return {name for name in os.listdir(root) if name.endswith(".spdx3.json")}


@pytest.fixture(autouse=True)
def _no_sbom_left_in_cwd() -> Iterator[None]:
    """Fail a test that leaves a ``*.spdx3.json`` in the working directory it
    started in (a run without ``-o`` writes the SBOM there); remove it."""
    root = os.getcwd()
    before = _sboms_in(root)
    yield
    left = sorted(_sboms_in(root) - before)
    for name in left:
        os.remove(os.path.join(root, name))
    assert not left, f"SBOM left in the working directory, pass -o: {left}"


@pytest.fixture(autouse=True)
def _restore_int_digit_limit() -> Iterator[None]:
    """Put CPython's ``int_max_str_digits`` back after each test: a test may
    change it with ``sys.set_int_max_str_digits``, and it is process-global.
    CPython 3.10.0-3.10.6 has no such limit."""
    getter = getattr(sys, "get_int_max_str_digits", None)
    setter = getattr(sys, "set_int_max_str_digits", None)
    saved = getter() if getter is not None else None
    yield
    if setter is not None:
        setter(saved)


@pytest.fixture(autouse=True)
def _block_network_access(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Block real outbound sockets during tests, by default.

    Several code paths (PyPI JSON API dependency enrichment, remote
    ``AUTHORS`` file fetches) make real network requests unless the caller
    threads ``offline=True`` all the way through -- which not every test
    does. Without this guard, a forgotten mock silently turns into a
    live network call: slow, flaky, and broken in offline/CI-sandboxed
    runs. Tests that genuinely need a live socket opt out via the
    ``network`` marker. A ``loopback`` test may open sockets, but only to this
    machine (a server the test starts): the in-process ``connect`` and
    ``connect_ex`` refuse any other address, and no proxy variable of the
    machine applies (``tests._network.bypass_proxies``). A DNS lookup, a UDP
    send and a subprocess are not covered.
    """
    if "network" in request.keywords:
        return
    monkeypatch.setattr(
        "pitloom.assemble.spdx3.deps_pypi._fetch_pypi_release_info",
        lambda name, version: None,
    )
    if "loopback" in request.keywords:
        bypass_proxies(monkeypatch)
        monkeypatch.setattr(
            socket.socket, "connect", _loopback_only(socket.socket.connect)
        )
        monkeypatch.setattr(
            socket.socket, "connect_ex", _loopback_only(socket.socket.connect_ex)
        )
        return
    monkeypatch.setattr(socket, "socket", _blocked_socket)


@pytest.fixture
def offline_spdx3_validate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run ``spdx3_validate.validate`` against the vendored model, no network."""
    use_offline_model(monkeypatch)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Iterator[None]:
    """Each phase's report: a skipped ``network`` test made a failure in
    strict mode (:func:`tests._network.fail_skipped_network_test`), then the
    call phase's outcome kept for the strict check
    (:func:`tests._strict_uncoded.note_call_report`)."""
    del call
    outcome: Any = yield
    report = outcome.get_result()
    fail_skipped_network_test(item, report)
    note_call_report(item, report)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark the OS-dependent test files ``platform`` (tests/_platform.py)."""
    root = Path(__file__).parent
    for item in items:
        if is_platform_file(item.path, root):
            item.add_marker(pytest.mark.platform)


@pytest.hookimpl(wrapper=True)
def pytest_fixture_setup(
    fixturedef: pytest.FixtureDef[Any], request: pytest.FixtureRequest
) -> Iterator[Any]:
    """Hold a module-, class- or session-scoped fixture's setup and teardown
    to the strict check (:class:`tests._strict_uncoded.FixtureWatch`): a
    finding errors the test that set it up or tore it down. The teardown
    window is two finalizers around the fixture's own (they run LIFO)."""
    del request
    if fixturedef.scope == "function":
        return (yield)
    name = f"{fixturedef.argname!r} ({fixturedef.scope}, {fixturedef.baseid})"
    fixturedef.addfinalizer(functools.partial(_FIXTURE_WATCH.leave, name, "teardown"))
    _FIXTURE_WATCH.enter()
    try:
        return (yield)
    finally:
        fixturedef.addfinalizer(_FIXTURE_WATCH.enter)
        _FIXTURE_WATCH.leave(name, "setup")
