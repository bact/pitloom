# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard on the prose about a line without a code: the user guide
(``docs/messages.md``) and each skill's ``references/messages.md`` name every
prefix of :data:`pitloom.messages.RELAY_PREFIXES` (another tool's words, said
after its name) in backticks, as the line prints it (`` `licenseid: ` ``), in
the hand-written text above the generated block. A new relay prefix fails here
until the three pages name it.

See also: tests/messages/test_line_kind.py (reading a relay line back),
tests/messages/test_generated_reference.py (the generated block).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pitloom.messages import RELAY_PREFIXES

pytestmark = pytest.mark.platform

_ROOT = Path(__file__).resolve().parents[2]
_PAGES = (
    _ROOT / "docs" / "messages.md",
    _ROOT / "skills" / "sbom-generate" / "references" / "messages.md",
    _ROOT / "skills" / "sbom-enrich" / "references" / "messages.md",
)
#: Where the generated block of a page starts.
_BLOCK = "<!-- BEGIN GENERATED"


def _prose(page: Path) -> str:
    """The hand-written text of *page* above its generated block (the whole
    page when it has none), its whitespace runs collapsed so a wrapped span
    still matches."""
    text = page.read_text(encoding="utf-8").split(_BLOCK)[0]
    return re.sub(r"\s+", " ", text)


@pytest.mark.parametrize("page", _PAGES, ids=lambda p: p.parent.parent.name)
@pytest.mark.parametrize(
    "prefix", RELAY_PREFIXES, ids=lambda p: p.removesuffix(": ").replace(" ", "-")
)
def test_the_prose_names_each_relay_prefix(page: Path, prefix: str) -> None:
    """Each prefix is in backticks, name then ``: ``, as a line prints it."""
    name = prefix.removesuffix(": ")
    assert name != prefix, "a relay prefix ends in a colon and a space"
    assert f"`{name}: `" in _prose(page)


def test_the_prefixes_to_name_are_the_four_relays() -> None:
    """The set the pages must name, so a trimmed list cannot pass them."""
    assert {p.removesuffix(": ") for p in RELAY_PREFIXES} == {
        "licenseid",
        "setuptools stderr",
        "fickling",
        "spdx3-validate",
    }
