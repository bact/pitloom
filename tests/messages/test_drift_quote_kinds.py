# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard on every ``LEVEL:`` quote of the docs and the skills, a
family marker in it or not: each is a kind of line Pitloom prints
(:func:`tests._message_quotes.quote_kind`), or another tool's line named in
:data:`_EXTERNAL`. A quote holding a marker is matched against its family in
tests/messages/test_drift_quotes.py; this module reads the rest.

See also: tests/messages/test_drift_quotes.py, tests/_message_quotes.py.
"""

from __future__ import annotations

import re
from collections import Counter

import pytest

from tests._docs_scan import CLI_DOC_FILES, read
from tests._message_drift import relative
from tests._message_quotes import (
    CATALOGUED,
    CODED,
    DETAIL,
    MARKED,
    PREFIX,
    RELAY,
    SUMMARY,
    quote_kind,
    quote_matches,
)
from tests.messages.test_drift_quotes import _FENCE, _MARKERS, _SPAN

#: Quotes of another tool's own lines, (file, quote) to the tool that prints
#: them. Shrink only.
_EXTERNAL: dict[tuple[str, str], str] = {
    (
        "skills/sbom-generate/references/known-limitations.md",
        "WARNING: popularity.csv: missing",
    ): "licenseid update",
    (
        "skills/sbom-validate/references/examples.md",
        "ERROR: JSON Schema validation failed for <file>:",
    ): "spdx3-validate, run by hand",
    (
        "skills/sbom-validate/references/examples.md",
        "ERROR: SHACL Validation failed for <file>:",
    ): "spdx3-validate, run by hand",
}

_LEVEL_ANYWHERE = re.compile(r"(?:ERROR|WARNING|INFO): ")


def _level_quotes() -> list[tuple[str, str]]:
    """(file, quote) for each inline code span, wrapped lines joined, that
    holds ``LEVEL: ``."""
    found = []
    for path in CLI_DOC_FILES:
        text = _FENCE.sub("", read(path))
        for span in _SPAN.finditer(text):
            # A table cell escapes a pipe, in a code span too (GFM).
            quote = " ".join(span.group(2).replace("\\|", "|").split())
            if _LEVEL_ANYWHERE.search(quote):
                found.append((relative(path), quote))
    return found


_QUOTES = _level_quotes()
_UNMARKED = [(f, q) for f, q in _QUOTES if quote_kind(q, _MARKERS) != MARKED]


@pytest.mark.parametrize(
    ("file", "quote"), _UNMARKED, ids=[f"{f}:{q[:40]}" for f, q in _UNMARKED]
)
def test_every_level_quote_has_a_kind(file: str, quote: str) -> None:
    assert quote_kind(quote, _MARKERS) is not None or (file, quote) in _EXTERNAL, (
        f"{file}: {quote!r}"
    )


def test_the_kinds_cover_the_scan() -> None:
    """Every kind is still quoted somewhere, every quote has one, and each
    :data:`_EXTERNAL` entry still occurs and is read as no kind of ours."""
    kinds = Counter(quote_kind(q, _MARKERS) for _, q in _QUOTES)
    external = [(f, q) for f, q in _QUOTES if (f, q) in _EXTERNAL]
    assert kinds[None] == len(external)
    assert sum(kinds.values()) == len(_QUOTES)
    assert {MARKED, CODED, CATALOGUED, PREFIX, SUMMARY, RELAY, DETAIL} <= set(kinds)
    assert set(external) == set(_EXTERNAL)


_NO_MARKERS: dict[str, tuple[str, ...]] = {}


@pytest.mark.parametrize(
    ("quote", "kind"),
    [
        # a code: the line's level and code, or nothing
        (
            "INFO: FILE=<path> MODEL='<model>': model file name found "
            "[usage-unparseable/mention]",
            CODED,
        ),
        ("WARNING: FILE=<path> MODEL='<model>': model file name found ...", None),
        (
            "WARNING: FILE=<path> MODEL='<model>': model file name found "
            "[usage-unparseable/mention]",
            None,
        ),
        (
            "INFO: FILE=<path> MODEL='<model>': model file name found "
            "[reader-unsafe/remote]",
            None,
        ),
        ("WARNING: ... [no-such-code]", None),
        ("WARNING: ... [credentials-unsafe/written]", CODED),
        ("INFO: ... [credentials-unsafe/written]", None),
        # no marker, no code: 12 literal characters in one family's line
        ("INFO: ... content changed ...", CATALOGUED),
        ("INFO: ... ontent chan ...", None),
        ("WARNING: ... content changed ...", None),
        # a frame or sub-prefix, then nothing or one wildcard
        ("WARNING: Build: ...", PREFIX),
        ("ERROR: loom <command>: ...", PREFIX),
        ("ERROR: Build: ...", None),
        ("WARNING: Bogus frame: ...", None),
        ("WARNING: :", None),
        ("ERROR: ...:", None),  # a wildcard is no frame
        ("INFO: hook:", None),  # text found only mid-line
        # a 12-character run two families print is no one entry's
        ("INFO: ... not recorded ...", None),
        # a summary, its nouns as printed
        ("INFO: ID registry: holds N id(s)", SUMMARY),
        ("INFO: ID registry: holds N file(s)", None),
        ("WARNING: ID registry: holds N id(s)", None),
        # a relay: at ERROR only after a frame
        ("ERROR: loom fragment validate: spdx3-validate: <line>", RELAY),
        ("ERROR: spdx3-validate: <line>", None),
        ("WARNING: licenseid: anything at all", RELAY),
        ("WARNING: ... anything at all", None),
        ("ERROR: ... spdx3-validate: <line>", None),
        ("WARNING: Build: licenseid: anything at all", RELAY),
        ("WARNING: Build: Git source: licenseid: x", None),
        # a -v detail
        ("INFO: OPTION=<name> SOURCE=<source> VALUE=<value>", DETAIL),
        ("INFO: OPTION=<name> SOURCE=<source>: no such line", None),
        ("WARNING: OPTION=<name> SOURCE=<source> VALUE=<value>", None),
        # no level
        ("ID registry: holds N id(s)", None),
    ],
    ids=lambda v: str(v)[:32],
)
def test_quote_kind_boundaries(quote: str, kind: str | None) -> None:
    assert quote_kind(quote, _NO_MARKERS) == kind


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        (
            "WARNING: ID registry: loom SDK model X has no path=; looked up ungated",
            True,
        ),
        ("ID registry: model X has no path=; looked up ungated", True),
        # with its level, a quote starts where the line starts: a free value
        # (the model's name) cannot hold the line's own start
        ("WARNING: ID registry: model X has no path=; looked up ungated", False),
    ],
    ids=["anchored", "piece", "mid-line"],
)
def test_a_quote_with_its_level_starts_the_line(quote: str, expected: bool) -> None:
    marker = "looked up ungated"
    assert quote_matches(quote, "registry-hash-missing", marker) is expected


def test_a_marker_makes_a_quote_marked() -> None:
    assert quote_kind("anything", {"f": ("thing",)}) == MARKED
    assert quote_kind("anything", {"f": ("other",)}) is None


_FAMILY_MARKERS = sorted((f, m) for f, markers in _MARKERS.items() for m in markers)


@pytest.mark.parametrize(
    ("family", "marker"), _FAMILY_MARKERS, ids=[f"{f}:{m}" for f, m in _FAMILY_MARKERS]
)
def test_every_marker_can_print(family: str, marker: str) -> None:
    """A marker no line prints alone marks no quote that can match."""
    assert quote_matches(marker, family, marker)
