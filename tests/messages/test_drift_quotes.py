# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard on the docs and the skills: a backticked quote that holds a
catalogued family's marker text is a piece of one of its patterns, at a level
and with a code the entry has. Wording changes in the catalogue fail here
until the quote follows.

A quote may leave text out (``...``), name a value (``<path>``, ``%s``,
``(N files)``, ``byte(s)``), start with ``LEVEL: `` and end with `` [code]``.

See also: tests/messages/test_drift_sources.py, test_drift_records.py.
"""

from __future__ import annotations

import re

import pytest

from pitloom.messages import MESSAGES
from tests._docs_scan import CLI_DOC_FILES, read
from tests._message_drift import quote_matches, relative

#: The text that marks a quote as saying a family's message.
_MARKERS = {"lfs-pointer": "Git LFS pointer"}

#: Quotes of a tool's own lines, which no pattern here covers: (file, quote).
#: Shrink only.
_EXTERNAL: frozenset[tuple[str, str]] = frozenset()

_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.DOTALL)
_FENCE = re.compile(r"^[ \t]*```.*?^[ \t]*```", re.DOTALL | re.MULTILINE)


def _quotes() -> list[tuple[str, str, str]]:
    """(file, family, quote) for each inline code span, wrapped lines joined,
    that holds a family's marker."""
    found = []
    for path in CLI_DOC_FILES:
        text = _FENCE.sub("", read(path))
        for span in _SPAN.finditer(text):
            quote = " ".join(span.group(2).split())
            for family, marker in _MARKERS.items():
                if marker in quote and (relative(path), quote) not in _EXTERNAL:
                    found.append((relative(path), family, quote))
    return found


def test_every_family_has_a_marker() -> None:
    assert {m.family for m in MESSAGES.values()} <= set(_MARKERS)


_QUOTES = _quotes()


def test_the_scan_found_quotes() -> None:
    files = {file for file, _, _ in _QUOTES}
    assert {
        "docs/messages.md",
        "skills/sbom-generate/references/known-limitations.md",
        "skills/sbom-generate/references/git-url.md",
    } <= files


@pytest.mark.parametrize(
    ("file", "family", "quote"),
    _QUOTES,
    ids=[f"{file}:{quote[:40]}" for file, _, quote in _QUOTES],
)
def test_a_quote_is_a_piece_of_the_catalogue(
    file: str, family: str, quote: str
) -> None:
    assert quote_matches(quote, family), f"{file}: {quote!r}"


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("WARNING: ... Git LFS pointer, content not read ... [lfs-pointer]", True),
        ("Git LFS pointer, content not read", True),
        ("WARNING: FILE=<first>: Git LFS pointer, content not read (N files);", True),
        (
            "ERROR: ... header is a Git LFS pointer, content not pulled "
            "(oid sha256:<oid>, size <N> byte(s)); run 'git lfs pull'",
            True,
        ),
        ("Git LFS pointer, content not read [lfs-pointer.shipped]", False),
        ("INFO: Git LFS pointer shipped; the build did not pull LFS content", False),
        ("WARNING: Git LFS pointer, content unread", False),
        ("Git LFS pointer is skipped", False),
    ],
    ids=lambda v: str(v)[:24],
)
def test_the_matcher_reads_elisions_and_checks_level_code_and_wording(
    quote: str, expected: bool
) -> None:
    assert quote_matches(quote, "lfs-pointer") is expected
