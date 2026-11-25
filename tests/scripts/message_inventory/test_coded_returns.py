# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``scripts/message_inventory``: a helper returning a coded exception is
judged by every value it returns, so ``raise helper(...)`` is coded only
when each branch is; a helper that returns no coded value keeps the body
rule; every coded exception class is a static marker, by its name alone.

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


def _at(records: list[dict[str, Any]], line: int) -> dict[str, Any]:
    (found,) = [
        r for r in records if r["module"] == "pitloom.refusals" and r["line"] == line
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


def test_the_two_branch_helper_counts_one_uncoded_site(
    mi: ModuleType, records: list[dict[str, Any]]
) -> None:
    assert mi.uncoded_counts(records) == {"pitloom.refusals": 1}
