# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The released-lines snapshot: every catalogued line a release prints, as
``code``, ``level`` and ``template`` separated by a tab, one row per line,
sorted, after a first line ``# released-lines <release>``. LF only, UTF-8.

The release bump writes it (``generate_message_reference.py --snapshot
<release>``); a test compares the catalogue with it, so a line absent from
the last release says the release that first prints it (``Line.since``).

Only :func:`write` imports Pitloom, when called: :func:`rows` and
:func:`dump` also read an older release's catalogue, imported from that
release's source.

See also: ``scripts/generate_message_reference.py`` (the ``--snapshot``
option) and ``tests/fixtures/message-catalogue/released-lines.tsv``.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final, Protocol

#: Where the snapshot lives, from the repository root.
SNAPSHOT: Final = Path("tests", "fixtures", "message-catalogue", "released-lines.tsv")
#: The first line's start, before the release.
_HEAD: Final = "# released-lines "
_RELEASE_RE: Final = re.compile(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}")

#: One row: a code, a level, a template.
Row = tuple[str, str, str]


class _Line(Protocol):
    """What a row reads of a catalogue line."""

    @property
    def level(self) -> str:
        """``ERROR``, ``WARNING`` or ``INFO``."""
        ...

    @property
    def template(self) -> str:
        """The text between ``LEVEL: `` and the code."""
        ...


# pylint: disable-next=too-few-public-methods
class _Message(Protocol):
    """What a row reads of a catalogue entry."""

    @property
    def lines(self) -> tuple[_Line, ...]:
        """Every shape it is printed in."""
        ...


def rows(messages: Mapping[str, _Message]) -> list[Row]:
    """Every line of *messages*, sorted.

    Raises:
        ValueError: A template holds a tab (it would split its row).
    """
    found = sorted(
        (code, ln.level, ln.template) for code, m in messages.items() for ln in m.lines
    )
    for row in found:
        if "\t" in row[2]:
            raise ValueError(f"{row[0]}: a template holds a tab: {row[2]!r}")
    return found


def dump(release: str, found: Iterable[Row]) -> bytes:
    """The snapshot of *found* for *release*.

    Raises:
        ValueError: *release* is not ``MAJOR.MINOR.PATCH``.
    """
    if _RELEASE_RE.fullmatch(release) is None:
        raise ValueError(f"release {release!r} is not MAJOR.MINOR.PATCH")
    text = "".join(f"{c}\t{lv}\t{t}\n" for c, lv, t in found)
    return f"{_HEAD}{release}\n{text}".encode()


def load(path: Path) -> tuple[str, frozenset[Row]]:
    """The release and the rows of the snapshot at *path*. The bytes are
    split on LF only, so the read is the same on every platform; every line
    ends in LF.

    Raises:
        ValueError: The first line or a row does not have its shape, a row
            is blank or there twice, or the last line has no LF.
    """
    head, *body = path.read_bytes().decode("utf-8").split("\n")
    release = head.removeprefix(_HEAD)
    if not head.startswith(_HEAD) or _RELEASE_RE.fullmatch(release) is None:
        raise ValueError(f"{path.name}: first line {head!r}")
    if not body or body.pop() != "":
        raise ValueError(f"{path.name}: the last line has no LF")
    found: set[Row] = set()
    for row in body:
        parts = row.split("\t")
        if len(parts) != 3 or "\r" in row:
            raise ValueError(f"{path.name}: row {row!r}")
        if (parts[0], parts[1], parts[2]) in found:
            raise ValueError(f"{path.name}: row {row!r} twice")
        found.add((parts[0], parts[1], parts[2]))
    return release, frozenset(found)


def write(root: Path, release: str) -> int:
    """Write the snapshot of the catalogue for *release* to :data:`SNAPSHOT`
    under *root*. The exit status: 0, 1 (a line first prints after
    *release*: nothing written) or 2 (*release* is not a release, or a
    template holds a tab)."""
    # pylint: disable-next=import-outside-toplevel
    from pitloom.messages import MESSAGES

    # pylint: disable-next=import-outside-toplevel
    from pitloom.messages._types import release_key

    try:
        data = dump(release, rows(MESSAGES))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    later = sorted(
        {
            code
            for code, m in MESSAGES.items()
            for ln in m.lines
            if release_key(ln.effective_since(m)) > release_key(release)
        }
    )
    if later:
        print(
            f"ERROR: {', '.join(later)}: a line first prints after {release}; "
            "not written",
            file=sys.stderr,
        )
        return 1
    path = root / SNAPSHOT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"INFO: {SNAPSHOT.as_posix()}: written for {release}", file=sys.stderr)
    return 0
