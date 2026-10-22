# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.core.frontmatter, the one frontmatter delimiter rule,
through each reader that uses it."""

# pylint: disable=protected-access

import logging
from pathlib import Path

import pytest

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.frontmatter import opens_frontmatter, split_frontmatter
from pitloom.enrich.readme import (
    MODEL_CARD_MAX_BYTES,
    ReadmeEnricher,
    _parse_frontmatter,
)
from pitloom.extract.remote._card_description import card_description

_SPLITS = [
    ("---\nlicense: mit\n---\nbody\n", ("license: mit\n", "body\n")),
    ("---\nlicense: a---b\n---\nx", ("license: a---b\n", "x")),
    ("---\nlicense: mit\n---\n", ("license: mit\n", "")),
    ("---\nlicense: mit\n---", ("license: mit\n", "")),
    ("---\nlicense: mit\n--- \t\nbody", ("license: mit\n", "body")),
    ("--- \nlicense: mit\n---\n", ("license: mit\n", "")),
    ("---\r\nlicense: mit\r\n---\r\nbody", ("license: mit\r\n", "body")),
    ("---\n---\nbody", ("", "body")),
    ("---\nlicense: mit\n-----\n---\nb", ("license: mit\n-----\n", "b")),
    ("\n \n---\nlicense: mit\n---\nb", ("license: mit\n", "b")),
    ("\ufeff---\nlicense: mit\n---\nb", ("license: mit\n", "b")),
    ("  ---\nlicense: mit\n  ---\nb", ("license: mit\n", "b")),
    ("  ---\nlicense: mit\n---\nb", None),
    ("---\nlicense: mit\n", None),
    ("---\nlicense: mit\n--- x\n", None),
    ("---\nlicense: mit\nmy---set\n", None),
    ("---\nlicense: [x---y]\n", None),
    ("---not\nlicense: mit\n---\n", None),
    ("-----\nlicense: mit\n---\n", None),
    ("prose\n---\nlicense: mit\n---\n", None),
]


@pytest.mark.parametrize(
    ("text", "expected"),
    _SPLITS,
    ids=[
        "basic", "dashes-in-value", "close-at-eof-newline", "close-at-eof",
        "trailing-space-close", "trailing-space-open", "crlf", "empty",
        "rule-inside",
        "blank-lead", "bom-lead", "indented", "indent-mismatch",
        "unclosed", "close-with-text", "midline-dashes",
        "flow-dashes", "open-with-text", "rule-open", "not-leading",
    ],
)  # fmt: skip
def test_split_frontmatter(text: str, expected: tuple[str, str] | None) -> None:
    assert split_frontmatter(text) == expected


def test_opens_frontmatter() -> None:
    assert opens_frontmatter("---\nx")
    assert opens_frontmatter("---  \r\nx")
    assert not opens_frontmatter("---not\nx")
    assert not opens_frontmatter("-----\nx")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("---\nlicense: my---set\n---\n", {"license": "my---set"}),
        ("---\nlicense: mit\nx: [a---b]\n---\n", {"license": "mit", "x": ["a---b"]}),
        ("---\r\nlicense: mit\r\n---\r\n", {"license": "mit"}),
        ("---\n---\n", None),
        ("---\nlicense: mit\n---", {"license": "mit"}),
    ],
    ids=["value-with-dashes", "flow-with-dashes", "crlf", "empty", "close-at-eof"],
)
def test_parse_frontmatter_uses_the_line_rule(
    text: str, expected: dict[str, object] | None
) -> None:
    assert _parse_frontmatter(text) == expected


@pytest.mark.parametrize(
    "lead",
    ["\n\n", "  \n", "\ufeff", "\ufeff\n"],
    ids=["blank", "spaces", "bom", "bom-blank"],
)
def test_both_readers_take_a_card_that_starts_with_blank_lines_or_a_bom(
    lead: str,
) -> None:
    """As the description reader always did (blank lines), and now the
    frontmatter reader too."""
    card = lead + "---\nlicense: mit\n---\n\nBody para.\n"
    assert _parse_frontmatter(card) == {"license": "mit"}
    assert card_description(card) == "Body para."


@pytest.mark.parametrize(
    "card",
    [
        "Just prose, no front matter.\n",
        "Intro paragraph.\n\n---\n\nAfter a rule.\n",
        "Intro.\n\n---\n\nMiddle.\n\n---\n\nEnd text.\n",
    ],
    ids=["none", "one-rule", "two-rules"],
)
def test_a_card_without_frontmatter_has_no_description_or_frontmatter(
    card: str,
) -> None:
    """A ``---`` rule in the body is no frontmatter: the first one used to
    open one, so a second rule made "End text." the description."""
    assert _parse_frontmatter(card) is None
    assert card_description(card) is None


def test_card_description_after_a_dashed_value() -> None:
    card = "---\nlicense: my---set\n---\n\nA real description.\n"
    assert card_description(card) == "A real description."
    assert card_description("---not\nlicense: a\n---\n\nProse here.\n") is None


@pytest.mark.parametrize(
    ("head", "read"),
    [
        ("---\nlicense: mit\n---\ny", True),
        ("---\nlicense: mit\nnote: a---b\n#", False),
        ("---\nlicense: mit\n-----\n#", False),
    ],
    ids=["closing-line", "dashes-inside-a-line", "rule-not-a-delimiter"],
)
def test_the_cap_check_uses_the_line_rule(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, head: str, read: bool
) -> None:
    """Over the cap, a frontmatter is closed only by a delimiter line: a
    ``---`` inside a line or a longer rule is no closing, so the card is
    skipped with its one warning rather than read as closed."""
    body = head + "x" * (MODEL_CARD_MAX_BYTES + 1 - len(head))
    (tmp_path / "README.md").write_text(body, encoding="ascii")
    model = AiModelMetadata()
    with caplog.at_level(logging.WARNING):
        ReadmeEnricher().enrich(model, model_dir=tmp_path)
    assert (model.license == "mit") is read
    assert bool(caplog.messages) is not read
