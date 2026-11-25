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
    log.warning(PREFIX + "%s", one_line(text), extra=RELAY_EXTRA)  # in: not-imported
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
from typing import Final

from pitloom.logging_config import one_line

log = logging.getLogger(__name__)
PREFIX = "tool: "
FINAL_PREFIX: Final = "tool: "
LIMIT = 200
LIMIT_TWICE = 1
LIMIT_TWICE = 2
FLAG = True
TEXT_LIMIT = "200"


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


def limits(text):
    log.warning(PREFIX + "%s", one_line(text, LIMIT))  # out: int-limit
    log.warning(PREFIX + "%s", one_line(text, 200))  # in: literal-limit
    log.warning(PREFIX + "%s", one_line(text, LIMIT_TWICE))  # in: limit-twice
    log.warning(PREFIX + "%s", one_line(text, FLAG))  # in: bool-limit
    log.warning(PREFIX + "%s", one_line(text, TEXT_LIMIT))  # in: text-limit
    log.warning(PREFIX + "%s", one_line(LIMIT, LIMIT))  # in: limit-as-text
    log.warning(PREFIX + "%s", one_line(text, LIMIT, LIMIT))  # in: three-args


def level_first(text, level):
    log.log(level, PREFIX + "%s", one_line(text))  # out: level-first
    log.log(level, FINAL_PREFIX + "%s", one_line(text))  # out: level-first-final


def annotated(text):
    log.warning(FINAL_PREFIX + "%s", one_line(text))  # out: final-prefix


def level_shapes(text, level):
    log.log(level, PREFIX + "%s", one_line(text), extra={})  # in: level-keyword
    log.log(level, PREFIX + "%s", one_line(text), one_line(text))  # in: level-two
    log.log(level, PREFIX + "%s")  # in: level-no-argument
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
#: The one keyword a prefixed relay may pass: ``extra=RELAY_EXTRA``.
_EXTRA = """\
import logging

from pitloom.logging_config import log_once, one_line
from pitloom.messages import RELAY_EXTRA, RELAY_FRAME
from pitloom.messages import RELAY_EXTRA as EXTRA

log = logging.getLogger(__name__)
PRE = "tool: "
OTHER = {}


def say(t, lv):
    log.warning(PRE + "%s", one_line(t), extra=RELAY_EXTRA)  # out: extra
    log.log(lv, PRE + "%s", one_line(t), extra=RELAY_EXTRA)  # out: level-extra
    log_once(log, lv, t, PRE + "%s", one_line(t), extra=RELAY_EXTRA)  # out: once
    log.warning(PRE + "%s", one_line(t), extra=OTHER)  # in: extra-other
    log.warning(PRE + "%s", one_line(t), extra=RELAY_FRAME)  # in: extra-frame
    log.warning(PRE + "%s", one_line(t), extra=EXTRA)  # in: extra-aliased
    log.warning(PRE + "%s", one_line(t), extra={**RELAY_EXTRA})  # in: extra-built
    log.warning(PRE + "%s", one_line(t), stacklevel=2)  # in: other-keyword
    log.warning(PRE + "%s", one_line(t), **RELAY_EXTRA)  # in: star-star
    log.warning(PRE + "%s", one_line(t), extra=RELAY_EXTRA, x=2)  # in: two-keywords


def rebound_in_function(t):
    RELAY_EXTRA = {"pitloom_code": "x"}
    log.warning(PRE + "%s", one_line(t), extra=RELAY_EXTRA)  # in: extra-rebound
"""
#: ``RELAY_EXTRA`` bound again at module level, or imported from elsewhere.
_EXTRA_REBOUND = """\
import logging

from pitloom.logging_config import one_line
from pitloom.messages import RELAY_EXTRA

log = logging.getLogger(__name__)
PRE = "tool: "
RELAY_EXTRA = {}


def say(t):
    log.warning(PRE + "%s", one_line(t), extra=RELAY_EXTRA)  # in: module-rebound
"""
_EXTRA_FOREIGN = """\
import logging

from pitloom.logging_config import one_line
from pitloom.other import RELAY_EXTRA

log = logging.getLogger(__name__)
PRE = "tool: "


def say(t):
    log.warning(PRE + "%s", one_line(t), extra=RELAY_EXTRA)  # in: extra-foreign
"""
_SOURCES = {
    "more.py": _MORE,
    "foreign.py": _FOREIGN,
    "rebound.py": _REBOUND,
    "extra.py": _EXTRA,
    "extra_rebound.py": _EXTRA_REBOUND,
    "extra_foreign.py": _EXTRA_FOREIGN,
}
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
