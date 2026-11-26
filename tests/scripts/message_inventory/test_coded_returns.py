# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``scripts/message_inventory``: a helper returning a coded exception is
judged by every value it returns, so ``raise helper(...)`` is coded only
when each branch is (each arm of a conditional, each operand of ``or``,
each value assigned to a returned name); a recursive call is not judged;
a helper that returns no coded value keeps the body rule; every coded
exception class is a static marker, by its name alone.

See also: test_inventory.py (the other coded-site rules) and
test_build_raise.py (a catalogue builder's raise).
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

MODULES = {
    "refusals.py": """\
import logging

from pitloom.messages import MSG, CodedOSError, CodedTypeError, CodedValueError

_log = logging.getLogger(__name__)


def mixed(path, reason):
    if reason:
        return CodedValueError(MSG, path=path)
    return ValueError(f"{path}: {reason}")


def every(path, reason):
    if reason is None:
        return None
    if reason:
        exc = CodedValueError(MSG, path=path)
        return exc
    return mixed_free(path)


def mixed_free(path, message=MSG):
    return CodedOSError(message, path=path)


def warn_and_flag(path):
    _log.warning("FILE=%s: odd", path, extra={"pitloom_code": MSG.code})
    return True


def run(path, reason):
    warn_and_flag(path)
    if reason == 1:
        raise mixed(path, reason)
    if reason == 2:
        raise every(path, reason)
    raise CodedTypeError(reason, path=path)
""",
    "branches.py": """\
from pitloom.messages import MSG, CodedValueError


def either(path, ok):
    return CodedValueError(MSG, path=path) if ok else ValueError(f"{path}: bad")


def reassigned(path, ok):
    exc = CodedValueError(MSG, path=path)
    if not ok:
        exc = ValueError(f"{path}: bad")
    return exc


def fallback(path, exc):
    return exc or CodedValueError(MSG, path=path)


def coded_or_none(path, ok):
    return CodedValueError(MSG, path=path) if ok else None


def recursive(path, depth):
    if depth:
        return recursive(path, depth - 1)
    return CodedValueError(MSG, path=path)


def ping(path, depth):
    if depth:
        return pong(path, depth - 1)
    return CodedValueError(MSG, path=path)


def pong(path, depth):
    if depth:
        return ping(path, depth - 1)
    return CodedValueError(MSG, path=path)


def outer(path, depth):
    if depth:
        return inner(path, depth - 1)
    return ValueError(f"{path}: bad")


def inner(path, depth):
    if depth:
        return outer(path, depth - 1)
    return CodedValueError(MSG, path=path)


def run(path, ok, depth):
    if depth == 1:
        raise either(path, ok)
    if depth == 2:
        raise reassigned(path, ok)
    if depth == 3:
        raise fallback(path, ok)
    if depth == 4:
        raise coded_or_none(path, ok)
    if depth == 5:
        raise recursive(path, depth)
    if depth == 6:
        raise ping(path, depth)
    if depth == 7:
        raise outer(path, depth)
    raise inner(path, depth)
""",
    "arms.py": """\
import logging

from pitloom.messages import MSG, CodedValueError, emit

_log = logging.getLogger(__name__)


def text_arm(path, ok):
    return CodedValueError(MSG, path=path) if ok else "plain"


def forwarded(path, code, ok):
    return CodedValueError(MSG, path=path) if ok else OSError(path, pitloom_code=code)


def said_then_plain(path):
    emit(_log, MSG, logging.WARNING, file=path)
    return ValueError(path)


def nested_plain(path):
    def inner():
        return ValueError(path)

    return CodedValueError(MSG, path=path)


def run(path, code, ok, which):
    if which == 1:
        raise text_arm(path, ok)
    if which == 2:
        raise forwarded(path, code, ok)
    if which == 3:
        raise said_then_plain(path)
    raise nested_plain(path)
""",
}


@pytest.fixture(name="records", scope="module")
def records_fixture(
    mi: ModuleType, tmp_path_factory: pytest.TempPathFactory
) -> list[dict[str, Any]]:
    """The sites of :data:`MODULES` under ``src/pitloom``."""
    root = tmp_path_factory.mktemp("coded-returns")
    package = root / "src" / "pitloom"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    for name, source in MODULES.items():
        (package / name).write_bytes(source.encode("utf-8"))
    return mi.inventory(Path(root))  # type: ignore[no-any-return]


def _at(
    records: list[dict[str, Any]], line: int, module: str = "refusals"
) -> dict[str, Any]:
    (found,) = [
        r for r in records if r["module"] == f"pitloom.{module}" and r["line"] == line
    ]
    return found


@pytest.mark.parametrize(
    ("line", "coded"),
    [(33, True), (35, False), (37, True), (38, True)],
    ids=["log-helper", "one-uncoded-return", "every-return", "type-error"],
)
def test_a_helper_is_coded_only_when_every_return_is(
    records: list[dict[str, Any]], line: int, coded: bool
) -> None:
    """``mixed`` has one coded and one plain return: its raise is uncoded.
    ``every`` returns ``None``, a coded name and an in-package coded call:
    coded. A helper returning ``True`` after a coded log keeps its code."""
    assert _at(records, line)["coded"] is coded


@pytest.mark.parametrize(
    ("helper", "coded"),
    [
        ("either", False),
        ("reassigned", False),
        ("fallback", False),
        ("coded_or_none", True),
        ("recursive", True),
        ("ping", True),
        ("outer", False),
        ("inner", False),
    ],
)
def test_each_branch_of_a_return_is_judged(
    records: list[dict[str, Any]], helper: str, coded: bool
) -> None:
    """Each arm of a conditional, each operand of ``or`` and each value
    assigned to a returned name must be coded; a ``None`` arm and a call
    back into the helper (or its partner) are not judged. ``inner``, judged
    first while ``outer`` was open, is judged again: ``outer`` is uncoded."""
    lines = MODULES["branches.py"].splitlines()
    (line,) = [n for n, text in enumerate(lines, 1) if f" raise {helper}(" in text]
    assert _at(records, line, "branches")["coded"] is coded


@pytest.mark.parametrize(
    ("helper", "coded", "forwards"),
    [
        ("text_arm", False, False),
        ("forwarded", False, True),
        ("said_then_plain", True, False),
        ("nested_plain", True, False),
    ],
)
def test_a_return_arm_that_is_no_coded_value(
    records: list[dict[str, Any]], helper: str, coded: bool, forwards: bool
) -> None:
    """A text arm is not "no message"; an arm forwarding a code makes the
    site a forwarder; a helper that says a coded line keeps the body rule;
    a nested function's return is not the helper's."""
    lines = MODULES["arms.py"].splitlines()
    (line,) = [n for n, text in enumerate(lines, 1) if f" raise {helper}(" in text]
    found = _at(records, line, "arms")
    assert (found["coded"], found["forwards_code"]) == (coded, forwards)


def test_the_two_branch_helper_counts_one_uncoded_site(
    mi: ModuleType, records: list[dict[str, Any]]
) -> None:
    assert mi.uncoded_counts(records)["pitloom.refusals"] == 1
