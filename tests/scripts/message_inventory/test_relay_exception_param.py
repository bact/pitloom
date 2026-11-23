# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``scripts/message_inventory/_relay.py``, the ``exception-param`` relay
(rule R-b): a function whose only statement says the exception it is handed
(a parameter annotated with an exception class, no default), its own text
by ``str()`` and code, is out of scope; text of its own, a bare parameter,
another parameter or a second statement keeps it counted.

Each case is a line of :data:`SOURCE` ending in ``# in: <id>`` (the ratchet
counts it) or ``# out: <id>`` (it does not).

See also: test_relay_scope.py (the catch-all handler's relay).
"""

from __future__ import annotations

import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SOURCE = '''\
import json
import logging
import zipfile

from pitloom.logging_config import print_error
from pitloom.messages import code_of

log = logging.getLogger(__name__)
other = None
DEFAULT = ValueError()
errors = None


def reporter(exc: Exception):
    """Say *exc*."""
    print_error(str(exc), code=code_of(exc))  # out: docstring


def reporter_bare(exc: ValueError | OSError):
    print_error(str(exc), code=code_of(exc))  # out: no-docstring


def reporter_fallback(exc: BaseException):
    print_error(str(exc) or type(exc).__name__, code=code_of(exc))  # out: fallback


def reporter_kwonly(*, exc: json.JSONDecodeError | errors.CodedError):
    print_error(str(exc), code=code_of(exc))  # out: kwonly


def report_error_line(exc: Exception) -> None:
    """Pitloom's own reporter."""
    print_error(str(exc), code=code_of(exc))  # out: report-error-line


def not_named_error(exc: zipfile.BadZipFile):
    print_error(str(exc), code=code_of(exc))  # in: not-named-error


def bare_text(exc: Exception):
    print_error(exc, code=code_of(exc))  # in: bare-text


def plain_text(message: str):
    print_error(str(message), code=code_of(message))  # in: say-message


def unannotated(exc):
    print_error(str(exc), code=code_of(exc))  # in: unannotated


def half_union(exc: ValueError | str):
    print_error(str(exc), code=code_of(exc))  # in: half-union


def subscripted(exc: list[Exception]):
    print_error(str(exc), code=code_of(exc))  # in: subscripted


def defaulted(exc: Exception = DEFAULT):
    print_error(str(exc), code=code_of(exc))  # in: defaulted


def defaulted_kwonly(*, exc: Exception = DEFAULT):
    print_error(str(exc), code=code_of(exc))  # in: defaulted-kwonly


def default_on_other(exc: Exception, other_arg: int = 1):
    print_error(str(exc), code=code_of(exc))  # out: default-on-other


def constructed(path: str):
    exc = OSError(path)
    print_error(str(exc), code=code_of(exc))  # in: constructed


def own_text(exc: Exception):
    print_error(f"wheel: {exc}", code=code_of(exc))  # in: own-text


def two_statements(exc: Exception):
    log.info("x")
    print_error(str(exc), code=code_of(exc))  # in: two-statements


def call_then_more(exc: Exception):
    print_error(str(exc), code=code_of(exc))  # in: call-first
    log.info("x")


def wrapped(exc: Exception):
    list(print_error(str(exc), code=code_of(exc)))  # in: wrapped


def two_docstrings(exc: Exception):
    """One."""
    """Two."""
    print_error(str(exc), code=code_of(exc))  # in: two-docstrings


def not_a_param(exc: Exception):
    print_error(str(other), code=code_of(other))  # in: not-a-param


def no_code(exc: Exception):
    print_error(str(exc))  # in: no-code


def other_code(exc: Exception, err: Exception):
    print_error(str(exc), code=code_of(err))  # in: other-code


def returned(exc: Exception):
    return print_error(str(exc), code=code_of(exc))  # in: returned


class Reporter:
    def say(self, exc: Exception):
        print_error(str(exc), code=code_of(exc))  # out: method


print_error(str(other), code=code_of(other))  # in: module-level
'''

_MARK = re.compile(r"# (in|out): (\S+)$")
CASES = [
    (n, mark[0] == "in", mark[1])
    for n, line in enumerate(SOURCE.splitlines(), start=1)
    for mark in _MARK.findall(line)
]


@pytest.fixture(name="records", scope="module")
def records_fixture(
    mi: ModuleType, tmp_path_factory: pytest.TempPathFactory
) -> list[dict[str, Any]]:
    """The sites of :data:`SOURCE` as ``src/pitloom/reporters.py``."""
    root = tmp_path_factory.mktemp("reporters")
    package = root / "src" / "pitloom"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    (package / "reporters.py").write_bytes(SOURCE.encode("utf-8"))
    return mi.inventory(Path(root))  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("line", "scoped"),
    [(n, scoped) for n, scoped, _ in CASES],
    ids=[case_id for _, _, case_id in CASES],
)
def test_an_exception_reporter_is_out_of_scope_by_its_shape(
    mi: ModuleType, records: list[dict[str, Any]], line: int, scoped: bool
) -> None:
    (site,) = [r for r in records if r["line"] == line]
    assert mi.in_scope(site) is scoped
    assert (site["relays"] == "exception-param") is not scoped
