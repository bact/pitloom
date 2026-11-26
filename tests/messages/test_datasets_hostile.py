# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Hostile values in the shared dataset lines and ``text-unsafe``: a
dataset name or source read from a file stays one trusted, masked line of
bounded length (masked before the cut, escaped after), whatever it holds;
and the value checks keep their tri-state (absent and blank silent, a real
value kept, a wrong one warned once).

See also: :mod:`tests.messages.test_datasets` (the entries) and
:mod:`tests.messages.test_datasets_sites` (the call sites).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from collections.abc import Callable

import pytest

from pitloom.extract.dataset.values import (
    stated_count,
    stated_text,
    stated_texts,
    stated_url,
    stated_version,
)
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import trusted_message
from pitloom.messages._field_writers import NAME_CHARACTERS, NAME_CUT_MARK
from pitloom.messages.datasets import (
    NOT_TEXT,
    DatasetModel,
    say_one_dataset,
    warn_dataset_conflict,
    warn_dataset_field,
)
from pitloom.messages.text import warn_text_unsafe

_LOG = logging.getLogger("pitloom.datasets_hostile_test")
_SECRET = "pw-s3cr3t"
_HOSTILE = [
    "a\nWARNING: x [over-cap]",
    "\x1b[31mred\x1b[0m",
    "evil\u202etxt",
    f"https://u:{_SECRET}@h/d?token={_SECRET}",
    "x" * 1_000_000,
    'O\'Brien "Q" `b`',
    # masked before the cut, which falls inside the user information
    "x" * 481 + f"https://u:{_SECRET}@example.org/x",
]
_IDS = ["newline", "ansi", "bidi", "credential", "1mb", "quotes", "credential-at-cut"]

#: Each emitter of a name or source, by the code it says.
_EMITTERS: list[tuple[str, Callable[[str], None]]] = [
    ("dataset-field-invalid", lambda v: warn_dataset_field(_LOG, NOT_TEXT, v, "f", 1)),
    (
        "dataset-conflict",
        lambda v: warn_dataset_conflict(_LOG, DatasetModel(file="m"), v, "version"),
    ),
    (
        "dataset-conflict",
        lambda v: warn_dataset_conflict(_LOG, DatasetModel(name=v), v, "version"),
    ),
    ("dataset-conflict/spelling", lambda v: say_one_dataset(_LOG, v, v)),
    ("text-unsafe", lambda v: warn_text_unsafe(_LOG, ["dataset name"], dataset=v)),
]


def _printed(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        f"{r.levelname}: {r.getMessage()} [{getattr(r, CODE_ATTR)}]"
        for r in caplog.records
        if r.name == _LOG.name
    ]


@pytest.mark.parametrize("value", _HOSTILE, ids=_IDS)
@pytest.mark.parametrize(
    ("code", "say"), _EMITTERS, ids=[code for code, _ in _EMITTERS]
)
def test_a_hostile_value_stays_one_trusted_masked_cut_line(
    caplog: pytest.LogCaptureFixture,
    code: str,
    say: Callable[[str], None],
    value: str,
) -> None:
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        say(value)
    (printed,) = _printed(caplog)
    assert "\n" not in printed and "\x1b" not in printed and "\u202e" not in printed
    assert _SECRET not in printed
    found = trusted_message(printed)
    assert found is not None and found.code == code
    # two names at most, each cut, plus the line itself
    assert len(printed) < 2 * (NAME_CHARACTERS + len(NAME_CUT_MARK)) + 300
    if len(value) > NAME_CHARACTERS:
        assert NAME_CUT_MARK in printed


def test_a_source_holding_a_key_is_quoted_whole(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``SOURCE=`` is a quoted name: a source that reads as ``FIELD=...``
    cannot add a pair, and an empty source is the empty quotes."""
    forged = "c FIELD=license: a value of type int, not text; skipped"
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        warn_dataset_field(_LOG, NOT_TEXT, forged, "version", 1)
        warn_dataset_field(_LOG, NOT_TEXT, "", "url", 1)
    first, second = _printed(caplog)
    assert first.startswith(
        f"WARNING: dataset metadata: SOURCE='{forged}' FIELD=version: "
    )
    assert second.startswith("WARNING: dataset metadata: SOURCE='' FIELD=url: ")


def test_a_forged_code_reads_as_the_real_one(caplog: pytest.LogCaptureFixture) -> None:
    """A source ending in what reads as another code cannot give the line
    that code."""
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        warn_dataset_field(_LOG, NOT_TEXT, "s [over-cap]", "f", 1)
    (printed,) = _printed(caplog)
    found = trusted_message(printed)
    assert found is not None and found.code == "dataset-field-invalid"


@pytest.mark.parametrize(
    "call",
    [
        lambda: stated_text(None, "s", "f"),
        lambda: stated_text("", "s", "f"),
        lambda: stated_text("  ", "s", "f"),
        lambda: stated_text([], "s", "f"),
        lambda: stated_text([None], "s", "f"),
        lambda: stated_texts([None, ""], "s", "f"),
        lambda: stated_url("unknown", "s", "url"),
        lambda: stated_url(None, "s", "url"),
        lambda: stated_version("N/A", "s", numbers=False),
        lambda: stated_count(None, "s", "byte_size"),
    ],
    ids=[
        "none",
        "empty",
        "blank",
        "empty-list",
        "list-of-none",
        "blank-items",
        "url-placeholder",
        "url-none",
        "version-placeholder",
        "count-none",
    ],
)
def test_absent_blank_and_placeholder_are_silent(
    caplog: pytest.LogCaptureFixture, call: Callable[[], object]
) -> None:
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        assert call() in (None, [])
    assert not [r for r in caplog.records if r.levelno >= logging.INFO]


@pytest.mark.parametrize(
    ("value", "kept"),
    [(0, 0), ("0", 0), (3.0, 3), (-1, None), (True, None), (1.9, None), ("x", None)],
    ids=["zero", "zero-text", "integral-float", "negative", "true", "fraction", "text"],
)
def test_a_count_is_kept_or_warned_once(
    caplog: pytest.LogCaptureFixture, value: object, kept: int | None
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert stated_count(value, "s", "byte_size") == kept
    codes = [getattr(r, CODE_ATTR, None) for r in caplog.records]
    assert codes == ([] if kept is not None else ["dataset-field-invalid"])


def test_a_repeated_refused_item_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert stated_texts([1, 1, "a", 1], "s", "tags") == ["a"]
    assert [getattr(r, CODE_ATTR, None) for r in caplog.records] == [
        "dataset-field-invalid"
    ]


def test_a_1mb_source_is_cut_with_its_credential_masked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = "x" * 1_000_000 + f"https://u:{_SECRET}@h/x"
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        stated_text(5, source, "name")
    (record,) = caplog.records
    text = record.getMessage()
    assert _SECRET not in text and len(text) < NAME_CHARACTERS + 200
