# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.extract.remote._card_description.card_description`:
the first prose paragraph of a Hub model or dataset card.

See also: tests/extract/remote/test_huggingface_dataset.py (a dataset's
description) and tests/extract/remote/test_huggingface_metadata.py (a
model's).
"""

from __future__ import annotations

import pytest

from pitloom.extract.remote._card_description import (
    MAX_DESCRIPTION_CHARS,
    card_description,
)

_FRONT = "---\nlicense: mit\n---\n\n"
_MORE = "[More Information Needed](https://github.com/huggingface/datasets)"
_HOME = "https://rajpurkar.github.io/SQuAD-explorer/"
_SQUAD_SUMMARY = (
    "Stanford Question Answering Dataset (SQuAD) is a reading comprehension "
    "dataset, consisting of questions posed by crowdworkers on a set of "
    "Wikipedia articles."
)

# The opening of the Hub `squad` card: contents, then key lines, then prose.
_SQUAD = f"""# Dataset Card for "squad"

## Table of Contents
- [Dataset Card for "squad"](#dataset-card-for-squad)
  - [Table of Contents](#table-of-contents)
  - [Dataset Description](#dataset-description)
    - [Dataset Summary](#dataset-summary)

## Dataset Description

- **Homepage:** [{_HOME}]({_HOME})
- **Repository:** {_MORE}
- **Point of Contact:** {_MORE}
- **Size of downloaded dataset files:** 35.14 MB

### Dataset Summary

{_SQUAD_SUMMARY}
"""

# The `glue` card: a contents title without a heading, bare-URL key lines.
_GLUE = """# Dataset Card for GLUE

Table of Contents
* [Dataset Description](#dataset-description)
* [Dataset Structure](https://example.org/structure)

- **Homepage:** https://gluebenchmark.com/
- **Paper**: https://arxiv.org/abs/1804.07461

GLUE, the General Language Understanding Evaluation benchmark, is a
collection of resources for natural language understanding systems.
"""

# The `imdb` card: numbered contents, a rule, a table, then prose.
_IMDB = """1. [Dataset Summary](#dataset-summary)
2. [Languages](#languages)

---

| name | train | test |
|------|-------|------|
| plain_text | 25000 | 25000 |

Large Movie Review Dataset. This is a dataset for binary sentiment
classification.
"""

# A model card: centred logo, badges, a code block with a blank line.
_MODEL = """<p align="center">
  <img src="logo.png" width="200"/>
</p>

<!-- generated -->

[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE) ![CI](ci.svg)

```python

from transformers import AutoModel
```

A small model for **fast** text generation, see [the paper](https://x.org/p).
"""


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (_SQUAD, _SQUAD_SUMMARY),
        (
            _GLUE,
            "GLUE, the General Language Understanding Evaluation benchmark, is "
            "a collection of resources for natural language understanding "
            "systems.",
        ),
        (
            _IMDB,
            "Large Movie Review Dataset. This is a dataset for binary "
            "sentiment classification.",
        ),
        (
            _MODEL,
            "A small model for **fast** text generation, see [the paper]"
            "(https://x.org/p).",
        ),
    ],
    ids=["squad", "glue", "imdb", "model-html-badges-code"],
)
def test_non_prose_openings_are_passed_over(body: str, expected: str) -> None:
    assert card_description(_FRONT + body) == expected


@pytest.mark.parametrize(
    "body",
    [
        "# Title\n\n## Table of Contents\n- [A](#a)\n- [B](#b)\n",
        "**Paper:**\n**Repository:** [repo](https://x.org)\n",
        '<div align="center">\n<img src="logo.png">\n</div>\n',
        "```\n\nSome code comment.\n```\n",
        "***\n\n| a | b |\n",
        "",
    ],
    ids=["contents-only", "key-lines-only", "html", "fence", "rule-table", "empty"],
)
def test_no_prose_is_no_description(body: str) -> None:
    """Nothing is invented: a card of no prose has no description."""
    assert card_description(_FRONT + body) is None


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("A great model.", "A great model."),
        ("This is a powerful language model.",
         "This is a powerful language model."),
        ("A Thai-English bilingual reasoning model.",
         "A Thai-English bilingual reasoning model."),
        ("# Model\nA heading then prose.", "A heading then prose."),
        ("First line.\nSecond line.\n\nIgnored.", "First line. Second line."),
        ("First line of para.\n---\nSecond line.",
         "First line of para. --- Second line."),
        ("- [Docs](https://x.org/docs)\n- A list item of prose.",
         "- [Docs](https://x.org/docs) - A list item of prose."),
        ("**Summary:** A model for text generation.",
         "**Summary:** A model for text generation."),
        ("Contents of the box are listed below.",
         "Contents of the box are listed below."),
    ],
    ids=[
        "plain",
        "plain-metadata-suite",
        "plain-openthaigpt-suite",
        "heading-then-prose",
        "first-paragraph-only",
        "rule-mid-paragraph",
        "one-prose-item-keeps-the-list",
        "bold-key-with-a-sentence",
        "contents-in-prose",
    ],
)  # fmt: skip
def test_prose_is_kept_as_today(body: str, expected: str) -> None:
    """A paragraph with one line of prose is kept whole, as before (the
    model descriptions the rest of the suite reads included)."""
    assert card_description(_FRONT + body) == expected


@pytest.mark.parametrize(
    "card",
    ["Just prose, no front matter.", "---\nlicense: mit\n---\n"],
    ids=["no-front-matter", "front-matter-only"],
)
def test_no_body_is_no_description(card: str) -> None:
    assert card_description(card) is None


def test_a_long_paragraph_is_cut() -> None:
    description = card_description(_FRONT + "word " * 200)
    assert description is not None
    assert len(description) == MAX_DESCRIPTION_CHARS
