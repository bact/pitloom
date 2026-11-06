# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one lock of Pitloom's warning blocks and the per-thread recorder
(:mod:`pitloom.core.warning_capture`), with blocks of two threads in each
order.

See also: tests/extract/test_licenseid_relay.py (the LicenseID relay in
one thread).
"""

from __future__ import annotations

import logging
import threading
import warnings
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace, TracebackType
from typing import TextIO

import pytest

from pitloom.core import warning_capture
from pitloom.core._models_wheel_setuptools_relay import relay_setuptools_output
from pitloom.extract import _licenseid_relay, _usage_parse
from tests._licenseid_warn import warn_from_pitloom

_WAIT = 30.0
_SAID = "licenseid: database: build v2 outdated"


def _outdated() -> None:
    warn_from_pitloom("database", "build v2 outdated")


def _said(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == _licenseid_relay.__name__ and r.getMessage().startswith(_SAID)
    ]


def _shown(func: Callable[[], None]) -> list[str]:
    """What *func* gets shown, under ``always``."""
    with warnings.catch_warnings(record=True) as shown:
        warnings.simplefilter("always")
        func()
    return [str(w.message) for w in shown]


def test_only_this_threads_warnings_are_recorded() -> None:
    def run() -> None:
        with warning_capture.recorded_in_thread(lambda _: True) as caught:
            thread = threading.Thread(target=warnings.warn, args=("theirs",))
            thread.start()
            thread.join(_WAIT)
            warnings.warn("mine", stacklevel=1)
        assert [str(w.message) for w in caught] == ["mine"]

    assert _shown(run) == ["theirs"]


def test_left_in_place_out_of_order_it_records_nothing_more() -> None:
    """A block of other code entered inside and left outside puts the
    recorder back for good: it then forwards every warning."""

    def run() -> None:
        replaced = warnings.showwarning
        ours = ExitStack()
        caught = ours.enter_context(warning_capture.recorded_in_thread(bool))
        with warnings.catch_warnings(record=True):
            ours.close()  # ours is left first
        assert warnings.showwarning is not replaced  # the recorder, left in place
        warnings.warn("later", stacklevel=1)
        assert not caught

    assert _shown(run) == ["later"]


def test_it_puts_back_only_its_own_showwarning() -> None:
    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def theirs(
        message: Warning | str,
        category: type[Warning],
        filename: str,
        lineno: int,
        file: TextIO | None = None,
        line: str | None = None,
    ) -> None:
        del message, category, filename, lineno, file, line

    with warnings.catch_warnings():
        with warning_capture.recorded_in_thread(bool):
            warnings.showwarning = theirs
        assert warnings.showwarning is theirs


def test_an_overlapping_foreign_block_takes_the_lookup_warnings_but_leaks_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The limit the relay states: a ``catch_warnings(record=True)`` of
    other code, in another thread, entered while a lookup runs and left
    after it, takes what LicenseID warns meanwhile; once both are left,
    a warning is shown again, not taken into a list nobody reads."""
    entered, lookup_left = threading.Event(), threading.Event()
    foreign: list[warnings.WarningMessage] = []

    def other_code() -> None:
        with warnings.catch_warnings(record=True) as caught:
            entered.set()
            lookup_left.wait(_WAIT)
        foreign.extend(caught)

    def run() -> None:
        thread = threading.Thread(target=other_code)
        with _licenseid_relay.relay_licenseid_warnings():
            thread.start()
            entered.wait(_WAIT)
            _outdated()
        lookup_left.set()
        thread.join(_WAIT)
        warnings.warn("later", stacklevel=1)

    with caplog.at_level(logging.WARNING):
        assert _shown(run) == ["later"]
    assert [str(w.message) for w in foreign] == ["database: build v2 outdated"]
    assert not _said(caplog)


class _SpyLock:
    """The relay's lock, setting *tried* as a thread goes to take it."""

    def __init__(self, tried: threading.Event) -> None:
        self._tried = tried

    def __enter__(self) -> bool:
        self._tried.set()
        return warning_capture.WARNINGS_LOCK.__enter__()

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        warning_capture.WARNINGS_LOCK.__exit__(kind, value, trace)


@contextmanager
def _threads(*targets: Callable[[], None]) -> Iterator[None]:
    threads = [threading.Thread(target=target) for target in targets]
    for thread in threads:
        thread.start()
    try:
        yield
    finally:
        for thread in threads:
            thread.join(_WAIT)


def test_a_lookup_waits_for_the_setuptools_relay(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """A lookup begun inside the setuptools relay's block would put its
    filter into the filters that block throws away on exit: the host's
    ``ignore`` would then drop what LicenseID says."""
    inside, tried, release, left = (threading.Event() for _ in range(4))
    monkeypatch.setattr(_licenseid_relay, "WARNINGS_LOCK", _SpyLock(tried))

    def setuptools_block() -> None:
        with relay_setuptools_output(tmp_path):
            inside.set()
            release.wait(_WAIT)
        left.set()

    def lookup() -> None:
        inside.wait(_WAIT)
        with _licenseid_relay.relay_licenseid_warnings():
            tried.set()
            left.wait(_WAIT)
            _outdated()

    with warnings.catch_warnings(), caplog.at_level(logging.WARNING):
        warnings.simplefilter("ignore")
        with _threads(setuptools_block, lookup):
            tried.wait(_WAIT)
            release.set()
    assert len(_said(caplog)) == 1


def test_the_usage_parse_waits_for_a_lookup(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The usage scan's parse ignores every warning in its block; begun
    while a lookup runs, it would drop what LicenseID says meanwhile."""
    tried, release = threading.Event(), threading.Event()
    monkeypatch.setattr(_usage_parse, "WARNINGS_LOCK", _SpyLock(tried))

    def parse(source: str) -> object:
        tried.set()
        release.wait(_WAIT)
        return source

    monkeypatch.setattr(_usage_parse, "ast", SimpleNamespace(parse=parse))

    def lookup() -> None:
        thread = threading.Thread(target=_usage_parse.parse_python, args=("x = 1",))
        with _licenseid_relay.relay_licenseid_warnings():
            thread.start()
            tried.wait(_WAIT)
            _outdated()
            release.set()
        thread.join(_WAIT)

    with warnings.catch_warnings(), caplog.at_level(logging.WARNING):
        warnings.simplefilter("always")
        lookup()
    assert len(_said(caplog)) == 1
