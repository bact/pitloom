# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``scripts/message_inventory/_scope.py``: a raise of a ``DETAIL_EXC`` class
is detail, out of scope, by its name as written; a name no longer listed (a
bare ``ArgumentTypeError``, a model reader's own class, the ``_over_cap``
helper, the usage scan's ``_UsageOverCap``) stays counted outside a model
reader's package, and is detail inside it (its dispatch aside).

Each case is a line of :data:`SOURCE` ending in ``# in: <id>`` (the ratchet
counts it) or ``# out: <id>`` (it does not), placed in each of
:data:`FILES`.

See also: tests/messages/test_detail_classes.py (each listed class proved
through a surface), test_scope_os_error.py (rule R-a).
"""

from __future__ import annotations

import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SOURCE = """\
import argparse


def read(cap):
    raise argparse.ArgumentTypeError("t: no value")  # out: argparse-type
    raise argparse.ArgumentError(None, "a: no value")  # out: argparse-action
    raise ArgumentTypeError("bare: no value")  # in: bare-type
    raise ArgumentError(None, "bare: no action")  # in: bare-action
    raise MarkerShapeError("m: no gate")  # out: listed
    raise _OverCap(cap, "o: over")  # out: listed-private
    raise Malformed("r: bad header")  # in: reader-malformed
    raise ConfigShapeError("r: bad config")  # in: reader-config
    raise LimitExceeded("r: over a limit")  # in: reader-limit
    raise UnsupportedVersion("r: version 9")  # in: reader-version
    raise ModelLimitExceeded("r: over a model limit")  # in: reader-model-limit
    raise _UnsupportedAttribute("r: no attribute")  # in: reader-attribute
    raise _over_cap("h: over the count")  # in: helper
    raise _UsageOverCap("u: too deep")  # in: usage
    raise ValueError("v: plain")  # in: plain
"""
#: Where the source is placed: a module of Pitloom's, a model reader's
#: (whose raises are detail by where they are) and the readers' dispatch
#: (which is not).
FILES = {
    "writer": "src/pitloom/writer.py",
    "reader": "src/pitloom/extract/ai_model/gguf.py",
    "dispatch": "src/pitloom/extract/ai_model/reader.py",
}
_MARK = re.compile(r"# (in|out): (\S+)$")
CASES = [
    (where, n, mark[0] == "in" and where != "reader", mark[1])
    for where in FILES
    for n, line in enumerate(SOURCE.splitlines(), start=1)
    for mark in _MARK.findall(line)
]


@pytest.fixture(name="records", scope="module")
def records_fixture(
    mi: ModuleType, tmp_path_factory: pytest.TempPathFactory
) -> list[dict[str, Any]]:
    """The sites of :data:`SOURCE` in each of :data:`FILES`."""
    root = tmp_path_factory.mktemp("detail")
    for file in FILES.values():
        path = root / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(SOURCE.encode("utf-8"))
        for parent in path.relative_to(root / "src").parents:
            if parent.parts:
                (root / "src" / parent / "__init__.py").write_bytes(b"")
    return mi.inventory(Path(root))  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("where", "line", "scoped"),
    [(where, n, scoped) for where, n, scoped, _ in CASES],
    ids=[f"{where}-{case_id}" for where, _, _, case_id in CASES],
)
def test_a_raise_is_detail_by_its_listed_name_or_its_place(
    mi: ModuleType,
    records: list[dict[str, Any]],
    where: str,
    line: int,
    scoped: bool,
) -> None:
    (site,) = [r for r in records if r["file"] == FILES[where] and r["line"] == line]
    assert mi.in_scope(site) is scoped
    assert (mi.reach(site) == "detail") is not scoped
