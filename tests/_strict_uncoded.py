# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The strict check of the catalogue at run time: no line Pitloom says
without a code unless its kind has none by design.

Two legs, both applied to every test by the autouse
``_catalogued_records_are_valid`` fixture of ``tests/conftest.py``:

- a log record (``Logger.handle``): :func:`strict_finding` renders it with
  the command line's own formatter and reads the line back with
  :func:`pitloom.messages.line_kind`. A record at ``INFO`` or above on the
  logger ``pitloom`` or a ``pitloom.*`` one with no
  :data:`~pitloom.logging_config.CODE_ATTR` needs a
  :data:`~pitloom.logging_config.KIND_ATTR`, and its line must read back as
  that kind; a record never carries both; a line too long to be read back
  (``overlong``) is a finding whatever it carries;
- an ``ERROR:`` line of :func:`pitloom.logging_config.print_error`, seen
  through its one seam ``_write_error_line``: an ``uncoded`` or ``overlong``
  line is a finding (the validator's relay reads back as ``relay``).

A module-, class- or session-scoped fixture is set up before and torn down
after that function-scoped fixture, so ``pytest_fixture_setup`` in
``tests/conftest.py`` holds its setup and teardown to the same two legs
(:class:`FixtureWatch`); a finding errors the test that set the fixture up
or tore it down, and no marker allows it. Its hooks go in once, when
``tests/conftest.py`` is imported, under every per-test patch; a fixture a
test body sets up (``request.getfixturevalue``) is reported by the watch
alone (:attr:`FixtureWatch.watching`).

A test that says such a line on purpose names it with
``@pytest.mark.uncoded_output(*patterns)`` on the test or on its
``pytest.param`` (never a module or a class: only the item's own markers
count). Each pattern is a regular expression searched in the line; a line no
pattern matches fails the test, and so does a pattern that matches no line
(a stale allowance). :func:`check` is that rule, pure. A test whose call
phase did not run to an outcome (skipped in its body or in a fixture's
setup) is not held to its allowances: ``pytest_runtest_makereport`` in
``tests/conftest.py`` notes the call phase (:func:`note_call_report`) and
:func:`failures` reports no stale pattern unless it ran. The check fails at
fixture teardown, which pytest reports as ``XFAIL`` for an ``xfail`` test:
any finding in such a test, a stale allowance or an uncoded line, goes
unseen.

Silent gaps, by design or by cost:

- an ``INFO`` record never reaches ``Logger.handle`` while the ``pitloom``
  logger is unconfigured (``Logger.isEnabledFor`` is asked first, and the
  root logger's level is ``WARNING``): such a record is seen only in a test
  that configures logging or lowers a level (``caplog.at_level``);
- ``DEBUG`` records are out of scope, and so are a test's own
  ``pitloom.test_*`` loggers and third-party ones (``pitloomx`` too);
- a child process (``loom`` run as a script) and the GitHub Action are seen
  only through :func:`tests._loom_child.run_loom` and the manual CLI checks;
- a record is rendered without the handler's masking;
- a test that raises a logger's level or calls :func:`logging.disable`
  hides its ``WARNING``/``ERROR`` records from ``Logger.handle``;
- a direct ``print(..., file=sys.stderr)`` is never seen (the message
  inventory's ratchet catches it), nor an untagged child line (a traceback)
  under :func:`tests._loom_child.run_loom`;
- reading a line back is permissive by design: any ``INFO: KEY=`` line
  reads as detail, any text starting with a relay prefix as relay (Pitloom's
  own ``print_error("licenseid: ...")`` too), and a ``FORMAT=.. FILE=..``
  frame is accepted whatever its codes. The record leg is the tight one: a
  record needs its ``pitloom_kind``.

A record is blamed on the test running when it is handled: a thread an
earlier test left running may log into a later one, so each finding names
its logger and thread.

See also: tests/_message_drift.py (:func:`~tests._message_drift
.record_problem`), tests/messages/test_drift_strict.py.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from pitloom import logging_config
from pitloom.logging_config import (
    CODE_ATTR,
    DETAIL_KIND,
    KIND_ATTR,
    RELAY_KIND,
    SUMMARY_KIND,
    line_formatter,
)
from pitloom.messages import line_kind

#: A logger named like this belongs to a test that feeds the catalogue odd
#: text on purpose; its records are not checked.
TEST_LOGGER_PREFIX = "pitloom.test_"
#: The marker naming the lines a test says without a code on purpose.
MARKER = "uncoded_output"
#: The kinds a record without a code may carry.
RECORD_KINDS = frozenset({SUMMARY_KIND, DETAIL_KIND, RELAY_KIND})
#: The kinds of a printed line that fail unless allowed.
UNALLOWED_KINDS = frozenset({"uncoded", "overlong"})

#: The formatter of :func:`pitloom.logging_config.configure_logging`.
_FORMATTER = line_formatter()
#: Whether an item's call phase ran to an outcome, not skipped; absent when
#: it never started (:func:`note_call_report`).
CALL_RAN = pytest.StashKey[bool]()


@dataclass(frozen=True)
class Finding:
    """What the strict check found on one record or line: the *line* as
    printed, what is wrong with it, and whether a marker may allow it."""

    line: str
    problem: str
    allowable: bool = True


@dataclass(frozen=True)
class Verdict:
    """What :func:`check` found: lines no allowance matched, allowances
    that matched no line."""

    unallowed: tuple[str, ...]
    stale: tuple[str, ...]


def in_scope(name: str, level: int) -> bool:
    """Whether a record of logger *name* at *level* is checked: ``INFO`` or
    above, on ``pitloom`` or a ``pitloom.*`` logger not a test's own."""
    pitloom = name == "pitloom" or name.startswith("pitloom.")
    return level >= logging.INFO and pitloom and not name.startswith(TEST_LOGGER_PREFIX)


def rendered_line(record: logging.LogRecord) -> str:
    """*record* as the command line prints it, without a traceback: the
    formatter of :func:`pitloom.logging_config.configure_logging` (level
    tag, frame, escaped text, code) on a copy, so the record is untouched.
    A record whose message cannot be built renders as its level and the
    failure's class."""
    copy = logging.makeLogRecord(dict(record.__dict__))
    copy.exc_info, copy.exc_text, copy.stack_info = None, None, None
    try:
        return _FORMATTER.format(copy)
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        return f"{record.levelname}: (record not rendered: {type(exc).__name__})"


def _where(record: logging.LogRecord) -> str:
    """The logger and thread of *record*, for a finding's text."""
    return f"logger {record.name!r}, thread {record.threadName!r}"


def strict_finding(record: logging.LogRecord) -> Finding | None:
    """What the strict check finds wrong with *record*, or ``None``.

    A record with both a code and a kind, or a kind not one of
    :data:`RECORD_KINDS`, is wrong anywhere (no marker allows it). In scope
    (:func:`in_scope`): an uncoded record with no kind, a kind its line does
    not read back as, and a line too long to be read back."""
    code = getattr(record, CODE_ATTR, None)
    kind = getattr(record, KIND_ATTR, None)
    if record.name.startswith(TEST_LOGGER_PREFIX):
        return None
    if kind is not None and (code is not None or kind not in RECORD_KINDS):
        return Finding(
            rendered_line(record),
            f"a record with code {code!r} and kind {kind!r} ({_where(record)})",
            allowable=False,
        )
    if not in_scope(record.name, record.levelno):
        return None
    line = rendered_line(record)
    problem = _line_problem(line_kind(line), code, kind)
    if problem is None:
        return None
    return Finding(line, f"{problem} ({_where(record)})")


def _line_problem(read: str, code: object, kind: object) -> str | None:
    """What is wrong with a record of *code* and *kind* whose line reads
    back as *read*, or ``None``."""
    if read == "overlong":
        return "a line too long to read back"
    if code is not None:
        return None
    if kind is None:
        return "an uncoded record with no kind"
    if read != kind:
        return f"kind {kind!r} but the line reads as {read!r}"
    return None


def line_finding(line: str) -> Finding | None:
    """What the strict check finds wrong with *line*, one printed
    ``ERROR:`` line, or ``None``: it reads back as ``uncoded`` or
    ``overlong``."""
    read = line_kind(line)
    if read not in UNALLOWED_KINDS:
        return None
    thread = threading.current_thread().name
    return Finding(line, f"an {read} stderr line (thread {thread!r})")


def check(lines: Sequence[str], allowances: Sequence[str]) -> Verdict:
    """Which of *lines* no pattern of *allowances* matches
    (:func:`re.search`), and which patterns match none of *lines*.

    Raises:
        re.error: a pattern is not a regular expression.
    """
    patterns = [re.compile(pattern) for pattern in allowances]
    used = [False] * len(patterns)
    unallowed = []
    for line in lines:
        hits = [i for i, pattern in enumerate(patterns) if pattern.search(line)]
        for i in hits:
            used[i] = True
        if not hits:
            unallowed.append(line)
    stale = tuple(p for p, hit in zip(allowances, used, strict=True) if not hit)
    return Verdict(tuple(unallowed), stale)


def note_call_report(item: pytest.Item, report: pytest.TestReport) -> None:
    """Keep on *item* whether its call phase, which *report* may be, ran to
    an outcome (:data:`CALL_RAN`): ``False`` when it was skipped."""
    if report.when == "call":
        item.stash[CALL_RAN] = not report.skipped


def call_ran(item: pytest.Item) -> bool:
    """Whether *item*'s call phase ran to an outcome (:func:`note_call_report`)."""
    return item.stash.get(CALL_RAN, False)


def failures(
    findings: Sequence[Finding], allowances: Sequence[str], *, ran: bool = True
) -> list[str]:
    """Each failure of a test that made *findings* and allowed
    *allowances*: a finding no marker may allow, an allowable one no pattern
    matches, and, when the test *ran* (not skipped), a stale pattern."""
    hard = [f"{f.problem}: {f.line!r}" for f in findings if not f.allowable]
    soft = [f for f in findings if f.allowable]
    verdict = check([f.line for f in soft], allowances)
    unallowed = set(verdict.unallowed)
    hard += [f"{f.problem}: {f.line!r}" for f in soft if f.line in unallowed]
    if ran:
        hard += [f"stale allowance, matches no line: {p!r}" for p in verdict.stale]
    return hard


class FixtureWatch:
    """The strict check over a module-, class- or session-scoped fixture's
    setup and teardown, which the function-scoped check never sees:
    :meth:`enter` opens a window, :meth:`leave` closes it and fails on any
    finding in it. No marker allows one."""

    def __init__(self) -> None:
        self._open: list[list[str]] = []
        self._installed = False

    @property
    def watching(self) -> bool:
        """Whether a window is open: a finding now is this watch's to report."""
        return bool(self._open)

    def install(self) -> None:
        """Hook ``Logger.handle`` and ``_write_error_line`` for the session,
        once. Call it before any test patches either (at conftest import):
        installed under a per-test patch, the hook would take that patch for
        the original and go when the patch is undone."""
        if self._installed:
            return
        self._installed = True
        handle = logging.Logger.handle
        # pylint: disable-next=protected-access
        write = logging_config._write_error_line

        def watching(logger: logging.Logger, record: logging.LogRecord) -> None:
            self._note(strict_finding(record) if self._open else None)
            handle(logger, record)

        def watching_lines(line: str) -> None:
            self._note(line_finding(line) if self._open else None)
            write(line)

        logging.Logger.handle = watching  # type: ignore[method-assign,assignment]
        # pylint: disable-next=protected-access
        logging_config._write_error_line = watching_lines

    def _note(self, finding: Finding | None) -> None:
        if finding is not None and self._open:
            self._open[-1].append(f"{finding.problem}: {finding.line!r}")

    def enter(self) -> None:
        """Open a window: what is said until :meth:`leave` is checked.

        Raises:
            RuntimeError: :meth:`install` was not called.
        """
        if not self._installed:
            raise RuntimeError("FixtureWatch.install() not called")
        self._open.append([])

    def leave(self, fixture: str, when: str) -> None:
        """Close the last window, *when* (setup or teardown) of *fixture*;
        fail on any finding in it."""
        found = self._open.pop() if self._open else []
        if found:
            pytest.fail(
                f"uncoded output in the {when} of fixture {fixture}: "
                + "; ".join(found),
                pytrace=False,
            )
