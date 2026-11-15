# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A summary: an ``INFO:`` line of no condition, written from its fields
like a catalogued line, with no code on the record, never trusted as a
code's line, and listed on its topic's page of the generated reference.

See also: tests/scripts/message_inventory/test_summary_scope.py (the
ratchet leaves its calls out), tests/messages/test_generated_reference.py.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from pitloom.logging_config import CODE_ATTR
from pitloom.messages import SUMMARIES, Summary, say_summary, trusted_message
from pitloom.messages.id_registry_ids import DATASET_PATH_KEY

_LOG = logging.getLogger("pitloom.test_summaries")
_DOCS = Path(__file__).parents[2] / "docs"


@pytest.mark.parametrize(
    ("template", "topic", "meaning", "problem"),
    [
        ("%(entity)s first", "id-registry-ids", "m", "first"),
        ("held %(entity)s ", "id-registry-ids", "m", "white space at its end"),
        ("held %(entity)s", "no-such-topic", "m", "unknown topic"),
        ("held %(entity)s", "id-registry-ids", " ", "an empty meaning"),
    ],
    ids=["free-first", "trailing-space", "topic", "meaning"],
)
def test_a_summary_keeps_the_catalogues_rules(
    template: str, topic: str, meaning: str, problem: str
) -> None:
    with pytest.raises(ValueError, match=problem):
        Summary(template=template, meaning=meaning, topic=topic)


def test_say_summary_writes_its_fields_with_no_code(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A URL's credentials masked, a control character escaped: one line."""
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        say_summary(
            _LOG, DATASET_PATH_KEY, entity="https://u:SECRET@h/d\n.csv", name="d"
        )

    (record,) = caplog.records
    assert record.levelno == logging.INFO
    assert not hasattr(record, CODE_ATTR)
    text = record.getMessage()
    assert text == (
        "ID registry: dataset 'https://***:***@h/d\\n.csv' keyed by its path: d"
    )
    assert trusted_message(f"INFO: {text} [registry-path-key-unusable]") is None


def test_say_summary_refuses_another_field(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(ValueError):
        say_summary(_LOG, DATASET_PATH_KEY, entity="d")
    assert not caplog.records


def test_every_summary_is_on_its_topics_page() -> None:
    assert SUMMARIES
    for summary in SUMMARIES:
        assert summary.fields == frozenset(re.findall(r"%\((\w+)\)s", summary.template))
        page = (_DOCS / f"message-codes-{summary.topic}.md").read_text("utf-8")
        assert "## Summaries" in page
        assert summary.shown in page
