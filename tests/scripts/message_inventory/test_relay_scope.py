# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``scripts/message_inventory/_relay.py``: a site that says another's text
(the catch-all handler's line, ``argparse``'s own refusal) is out of scope
by the shape of the code around it, never by the name of a variable.

Each case is a line of :data:`SOURCE` ending in ``# in: <id>`` (the ratchet
counts it) or ``# out: <id>`` (it does not).

See also: test_inventory.py (the other scope rules),
tests/test_message_ratchet.py (the real tree's two relays).
"""

from __future__ import annotations

import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SOURCE = """\
import argparse
import logging
import sys
from argparse import ArgumentParser

from pitloom.logging_config import print_error
from pitloom.messages import code_of, other_code

log = logging.getLogger(__name__)
print_error(str(e), code=code_of(e))  # in: module-level


def handler(run, other):
    try:
        run()
    except Exception as e:
        print_error(str(e) or type(e).__name__, code=code_of(e))  # out: fallback
        print_error(str(e), code=code_of(e))  # out: str
        print_error(e, code=code_of(e))  # out: bare
        print_error(f"failed: {e}", code=code_of(e))  # in: own-text
        print_error(f"{e}")  # in: no-code
        print_error(str(e))  # in: str-no-code
        log.warning(f"{e}")  # in: log-warning
        log.error(str(e), code=code_of(e))  # in: not-print-error
        print_error(str(e), code=code_of(other))  # in: other-code
        print_error(str(other), code=code_of(e))  # in: other-text
        print_error(str(e), frame=code_of(e))  # in: not-code-kw
        print_error(str(e), code=other_code(e))  # in: not-code-of
        print_error(str(e), code=code_of(e, 1))  # in: code-of-two
        print_error(str(e), code=code_of(e.cause))  # in: code-of-attr
        print_error(repr(e), code=code_of(e))  # in: repr
        print_error(str(e, "x"), code=code_of(e))  # in: str-two
        print_error(str(e, errors="x"), code=code_of(e))  # in: str-kw
        print_error(str(e) and type(e).__name__, code=code_of(e))  # in: and
        print_error(str(e) or repr(e), code=code_of(e))  # in: or-repr
        print_error(repr(e) or type(e).__name__, code=code_of(e))  # in: or-first
        print_error(str(e) or type(e).__name__ or "x", code=code_of(e))  # in: or-3
    except BaseException as exc:
        print_error(str(exc), code=code_of(exc))  # out: base
    except (ValueError, OSError) as exc:
        print_error(str(exc), code=code_of(exc))  # in: narrow
    except ValueError as e:
        print_error(str(e), code=code_of(e))  # in: value-error
    print_error(str(e), code=code_of(e))  # in: outside


def no_handler(e):
    print_error(str(e), code=code_of(e))  # in: no-except
    try:
        e.run()
    except Exception as err:
        print_error(str(e), code=code_of(e))  # in: not-the-caught


def rebound(run, items, x):
    try:
        run()
    except Exception as e:
        e = RuntimeError("own text")
        print_error(str(e), code=code_of(e))  # in: assigned
    try:
        run()
    except Exception as e:
        if (e := RuntimeError("own text")):
            print_error(str(e), code=code_of(e))  # in: walrus
    try:
        run()
    except Exception as e:
        try:
            run()
        except ValueError as e:
            pass
        print_error(str(e), code=code_of(e))  # in: inner-except
    try:
        run()
    except Exception as e:
        import e.sub
        print_error(str(e), code=code_of(e))  # in: import
    try:
        run()
    except Exception as e:
        from x import y as e
        print_error(str(e), code=code_of(e))  # in: import-as
    try:
        run()
    except Exception as e:
        def helper(e):
            global x
        print_error(str(e), code=code_of(e))  # in: inner-param
    try:
        run()
    except Exception as e:
        def helper():
            global e
        print_error(str(e), code=code_of(e))  # in: global
    try:
        run()
    except Exception as e:
        match x:
            case {**e}:
                pass
        print_error(str(e), code=code_of(e))  # in: match-rest
    try:
        run()
    except Exception as e:
        f = lambda: print_error(str(e), code=code_of(e))  # in: lambda
    try:
        run()
    except Exception as e:
        f = lambda e: print_error(str(e), code=code_of(e))  # in: lambda-param
    try:
        run()
    except Exception as e:
        [print_error(str(e), code=code_of(e)) for y in items]  # in: comp
    try:
        run()
    except Exception as e:
        [print_error(str(e), code=code_of(e)) for e in items]  # in: comp-target
    try:
        run()
    except Exception as e:
        import os.path as p
        match x:
            case {"k": 1}:
                pass
            case _:
                pass
        print_error(str(e), code=code_of(e))  # out: other-bindings


class Parser(argparse.ArgumentParser):
    def error(self, message):
        print_error(message, frame="loom: ")  # out: parser
        print_error(f"bad: {message}")  # in: parser-own-text
        print_error(self.prog)  # in: parser-other-text

    def warn(self, message):
        print_error(message)  # in: not-error


class Imported(ArgumentParser):
    def error(self, text):
        print_error(text)  # out: imported-base


class Rebound(ArgumentParser):
    def error(self, message):
        message = "own words"
        print_error(message)  # in: parser-assigned


class OtherEmitters(ArgumentParser):
    def error(self, message):
        print(message, file=sys.stderr)  # in: parser-print
        log.error(message)  # in: parser-log
        f = lambda: print_error(message)  # in: parser-lambda
        raise RuntimeError(message)  # in: parser-raise

    def run(self, message):
        def error(self, message):
            print_error(message)  # in: nested-error


class ThreeArgs(ArgumentParser):
    def error(self, message, extra):
        print_error(message)  # in: three-params


class Other:
    def error(self, message):
        print_error(message)  # in: other-class


def error(self, message):
    print_error(message)  # in: plain-function
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
    """The sites of :data:`SOURCE` as ``src/pitloom/relays.py``."""
    root = tmp_path_factory.mktemp("relays")
    package = root / "src" / "pitloom"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    (package / "relays.py").write_bytes(SOURCE.encode("utf-8"))
    return mi.inventory(Path(root))  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("line", "scoped"),
    [(n, scoped) for n, scoped, _ in CASES],
    ids=[case_id for _, _, case_id in CASES],
)
def test_a_relay_is_out_of_scope_by_its_shape(
    mi: ModuleType, records: list[dict[str, Any]], line: int, scoped: bool
) -> None:
    (site,) = [r for r in records if r["line"] == line]
    assert mi.in_scope(site) is scoped
    assert bool(site["relays"]) is not scoped
