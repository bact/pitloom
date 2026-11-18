# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``scripts/message_inventory/_relay.py``, the ``prefixed`` relay: a
foreign tool's own words after Pitloom's sub-prefix (``licenseid: ``) are
out of scope by the shape of the call, never by a bare ``%s`` template.

Each case is a line of :data:`SOURCE` ending in ``# in: <id>`` (the ratchet
counts it) or ``# out: <id>`` (it does not).

See also: test_relay_scope.py (the other relays),
tests/test_message_ratchet.py (the real tree's relays).
"""

from __future__ import annotations

import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SOURCE = """\
import logging

from pitloom.logging_config import log_once, loggable, one_line

log = logging.getLogger(__name__)
PREFIX = "tool: "
TWICE = "tool: "
TWICE = "other: "
NOT_TEXT = 3


def say(text, level=logging.WARNING):
    log_once(log, level, text, PREFIX + "%s", one_line(text))  # out: relay
    log.warning(PREFIX + "%s", one_line(text))  # out: warning
    log.warning(PREFIX + "%s: own words", one_line(text))  # in: own-words
    log.warning(PREFIX + "%s", loggable(text))  # in: not-one-line
    log.warning(PREFIX + "%s", one_line(log))  # in: not-a-param
    log.warning(PREFIX + "%s", one_line(text), one_line(text))  # in: two-args
    log.warning(PREFIX + "%s", one_line(text), extra={})  # in: keyword
    log.warning(TWICE + "%s", one_line(text))  # in: prefix-bound-twice
    log.warning(NOT_TEXT + "%s", one_line(text))  # in: prefix-not-text
    log.warning("tool: " + "%s", one_line(text))  # in: literal-prefix
    log.warning(PREFIX + "%s", one_line(PREFIX))  # in: constant-text
    log.warning("%s", one_line(text))  # bare


def rebound(text):
    text = "own words"
    log.warning(PREFIX + "%s", one_line(text))  # in: rebound


def nested(text):
    def inner():
        log.warning(PREFIX + "%s", one_line(text))  # in: nested

    inner()


log.warning(PREFIX + "%s", one_line(SOURCE))  # in: module-level
"""

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
    """The sites of :data:`SOURCE` as ``src/pitloom/prefixed.py``."""
    root = tmp_path_factory.mktemp("prefixed")
    package = root / "src" / "pitloom"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    (package / "prefixed.py").write_bytes(SOURCE.encode("utf-8"))
    return mi.inventory(Path(root))  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("line", "scoped"),
    [(n, scoped) for n, scoped, _ in CASES],
    ids=[case_id for _, _, case_id in CASES],
)
def test_a_prefixed_relay_is_out_of_scope_by_its_shape(
    mi: ModuleType, records: list[dict[str, Any]], line: int, scoped: bool
) -> None:
    (site,) = [r for r in records if r["line"] == line]
    assert mi.in_scope(site) is scoped
    assert (site["relays"] == "prefixed") is not scoped


def test_a_bare_passthrough_is_no_relay(records: list[dict[str, Any]]) -> None:
    """``log.warning("%s", text)`` has no prefix naming whose words they
    are: never a relay, whatever else leaves it out of the count."""
    number = SOURCE.splitlines().index('    log.warning("%s", one_line(text))  # bare')
    (site,) = [r for r in records if r["line"] == number + 1]
    assert site["template"] == "%s" and not site["relays"]


_MORE = """\
import logging

from pitloom.logging_config import one_line

log = logging.getLogger(__name__)
PREFIX = "tool: "


def kwonly(*, text):
    log.warning(PREFIX + "%s", one_line(text))  # out: kwonly-param


def posonly(text, /):
    log.warning(PREFIX + "%s", one_line(text))  # out: posonly-param


async def asay(text):
    log.warning(PREFIX + "%s", one_line(text))  # out: async


def shapes(text):
    log.warning(PREFIX + "%s", one_line(text, text))  # in: one-line-two-args
    log.warning(PREFIX + "%s", one_line(text, end=""))  # in: one-line-keyword
    log.warning(PREFIX % "%s", one_line(text))  # in: not-a-sum
    log.warning(PREFIX + "%r", one_line(text))  # in: repr-template
"""
#: ``one_line`` imported from elsewhere.
_FOREIGN = """\
import logging

from pitloom.other import one_line

log = logging.getLogger(__name__)
PREFIX = "tool: "


def say(text):
    log.warning(PREFIX + "%s", one_line(text))  # in: foreign-one-line
"""
#: ``one_line`` bound again in the module.
_REBOUND = """\
import logging

from pitloom.logging_config import one_line

log = logging.getLogger(__name__)
PREFIX = "tool: "


def one_line(text):
    return text


def say(text):
    log.warning(PREFIX + "%s", one_line(text))  # in: one-line-rebound
"""
_SOURCES = {"more.py": _MORE, "foreign.py": _FOREIGN, "rebound.py": _REBOUND}
_MORE_CASES = [
    (name, n, mark[0] == "in", mark[1])
    for name, source in _SOURCES.items()
    for n, line in enumerate(source.splitlines(), start=1)
    for mark in _MARK.findall(line)
]


@pytest.fixture(name="more_records", scope="module")
def more_records_fixture(
    mi: ModuleType, tmp_path_factory: pytest.TempPathFactory
) -> list[dict[str, Any]]:
    """The sites of :data:`_SOURCES`, each as ``src/pitloom/<name>``."""
    root = tmp_path_factory.mktemp("prefixed-more")
    package = root / "src" / "pitloom"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    for name, source in _SOURCES.items():
        (package / name).write_bytes(source.encode("utf-8"))
    return mi.inventory(Path(root))  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("name", "line", "scoped"),
    [(name, n, scoped) for name, n, scoped, _ in _MORE_CASES],
    ids=[case_id for *_, case_id in _MORE_CASES],
)
def test_each_boundary_of_a_prefixed_relay(
    mi: ModuleType,
    more_records: list[dict[str, Any]],
    name: str,
    line: int,
    scoped: bool,
) -> None:
    (site,) = [
        r for r in more_records if r["file"].endswith(name) and r["line"] == line
    ]
    assert mi.in_scope(site) is scoped
    assert (site["relays"] == "prefixed") is not scoped
