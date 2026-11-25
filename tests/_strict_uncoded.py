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

A test that says such a line on purpose names it with
``@pytest.mark.uncoded_output(*patterns)`` on the test or on its
``pytest.param`` (never a module or a class: only the item's own markers
count). Each pattern is a regular expression searched in the line; a line no
pattern matches fails the test, and so does a pattern that matches no line
(a stale allowance). :func:`check` is that rule, pure.

Silent gaps, by design or by cost:

- an ``INFO`` record never reaches ``Logger.handle`` while the ``pitloom``
  logger is unconfigured (``Logger.isEnabledFor`` is asked first, and the
  root logger's level is ``WARNING``): such a record is seen only in a test
  that configures logging or lowers a level (``caplog.at_level``);
- ``DEBUG`` records are out of scope, and so are a test's own
  ``pitloom.test_*`` loggers and third-party ones (``pitloomx`` too);
- a child process (``loom`` run as a script) and the GitHub Action are seen
  only through :func:`tests._loom_child.run_loom` and the manual CLI checks;
- a record is rendered without the handler's masking.

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

from pitloom.logging_config import (
    CODE_ATTR,
    DETAIL_KIND,
    KIND_ATTR,
    RELAY_KIND,
    SUMMARY_KIND,
    _OneLineFormatter,
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
_FORMATTER = _OneLineFormatter("%(levelname)s: %(message)s")


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

    A record with both a code and a kind is wrong anywhere (no marker allows
    it). In scope (:func:`in_scope`): an uncoded record with no kind, a kind
    that is not one of :data:`RECORD_KINDS` or that its line does not read
    back as, and a line too long to be read back."""
    code = getattr(record, CODE_ATTR, None)
    kind = getattr(record, KIND_ATTR, None)
    if record.name.startswith(TEST_LOGGER_PREFIX):
        return None
    if code is not None and kind is not None:
        return Finding(
            rendered_line(record),
            f"a record with both code {code!r} and kind {kind!r} ({_where(record)})",
            allowable=False,
        )
    if not in_scope(record.name, record.levelno):
        return None
    line = rendered_line(record)
    read = line_kind(line)
    if read == "overlong":
        return Finding(line, f"a line too long to read back ({_where(record)})")
    if code is not None:
        return None
    if kind is None:
        return Finding(line, f"an uncoded record with no kind ({_where(record)})")
    if kind not in RECORD_KINDS:
        return Finding(
            line, f"unknown kind {kind!r} ({_where(record)})", allowable=False
        )
    if read != kind:
        return Finding(
            line, f"kind {kind!r} but the line reads as {read!r} ({_where(record)})"
        )
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


def failures(findings: Sequence[Finding], allowances: Sequence[str]) -> list[str]:
    """Each failure of a test that made *findings* and allowed
    *allowances*: a finding no marker may allow, an allowable one no pattern
    matches, and a stale pattern."""
    hard = [f"{f.problem}: {f.line!r}" for f in findings if not f.allowable]
    soft = [f for f in findings if f.allowable]
    verdict = check([f.line for f in soft], allowances)
    unallowed = set(verdict.unallowed)
    hard += [f"{f.problem}: {f.line!r}" for f in soft if f.line in unallowed]
    hard += [f"stale allowance, matches no line: {p!r}" for p in verdict.stale]
    return hard
